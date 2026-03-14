from django.core.management.base import BaseCommand
from integrations.tallysync.models import TallyCompany
from integrations.tallysync.services.sync_service import TallySyncService


class Command(BaseCommand):
    help = 'Sync single company currently selected in Tally'

    def add_arguments(self, parser):
        parser.add_argument('company_name', type=str, help='Company name to sync')

    def handle(self, *args, **options):
        company_name = options['company_name']
        service = TallySyncService()
        
        # Test connection
        self.stdout.write("Testing Tally connection...")
        if not service.test_connection():
            self.stdout.write(self.style.ERROR('❌ Cannot connect to Tally'))
            return
        
        self.stdout.write(self.style.SUCCESS('✅ Connected to Tally'))
        
        # Get or create company
        company, created = TallyCompany.objects.get_or_create(name=company_name)
        
        if created:
            self.stdout.write(f"Created new company: {company_name}")
        
        # Sync master data
        self.stdout.write(f"\nSyncing master data for: {company_name}")

        result = service.sync_groups(company, triggered_by_user='management_command')
        self.stdout.write(f"📁 Groups: {result['created']} created, {result['updated']} updated")

        result = service.sync_ledgers(company, triggered_by_user='management_command')
        self.stdout.write(f"📒 Ledgers: {result['created']} created, {result['updated']} updated")

        result = service.sync_cost_centres(company, triggered_by_user='management_command')
        self.stdout.write(f"🎯 Cost Centres: {result['created']} created, {result['updated']} updated")
        
        self.stdout.write(self.style.SUCCESS('\n✅ Sync completed!'))