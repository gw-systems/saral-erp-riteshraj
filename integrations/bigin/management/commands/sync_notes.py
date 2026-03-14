from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
from integrations.bigin.models import BiginContact
from integrations.bigin.bigin_sync import fetch_contact_notes
import time
from datetime import timedelta


class Command(BaseCommand):
    help = 'Fetch and cache notes for all Bigin contacts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of contacts to sync (for testing)'
        )
        parser.add_argument(
            '--owner',
            type=str,
            default=None,
            help='Only sync notes for specific owner (e.g., "Ravi Moolya")'
        )

    def handle(self, *args, **options):
        limit = options.get('limit')
        owner = options.get('owner')
        
        # Get contacts without notes or with stale notes (>7 days old)
        stale_date = timezone.now() - timedelta(days=7)
        
        contacts = BiginContact.objects.filter(module='Contacts')
        
        if owner:
            contacts = contacts.filter(owner__icontains=owner)
        
        # Filter: no notes OR stale notes
        contacts = contacts.filter(
            Q(notes__isnull=True) | 
            Q(notes='') | 
            Q(notes='[No Notes Found]') |
            Q(notes_fetched_at__lt=stale_date) |
            Q(notes_fetched_at__isnull=True)
        ).order_by('-created_time')
        
        if limit:
            contacts = contacts[:limit]
        
        total = contacts.count()
        self.stdout.write(f"🔄 Starting notes sync for {total} contacts...")
        
        success = 0
        errors = 0
        
        for idx, contact in enumerate(contacts, 1):
            try:
                # Fetch notes from API
                notes = fetch_contact_notes(contact.bigin_id)
                
                # Update contact
                contact.notes = notes
                contact.notes_fetched_at = timezone.now()
                contact.save(update_fields=['notes', 'notes_fetched_at'])
                
                success += 1
                
                # Progress update every 10 contacts
                if idx % 10 == 0:
                    self.stdout.write(f"  Progress: {idx}/{total} ({success} success, {errors} errors)")
                
                # Rate limiting: 2 requests per second max
                time.sleep(0.5)
                
            except Exception as e:
                errors += 1
                self.stdout.write(self.style.ERROR(f"  ❌ Error for {contact.bigin_id}: {str(e)}"))
        
        self.stdout.write(self.style.SUCCESS(f"\n✅ Notes sync complete!"))
        self.stdout.write(f"   Total: {total} | Success: {success} | Errors: {errors}")
