"""
Django management command to fix supply app migrations.

This command removes fake migration records from django_migrations table
and re-runs the migrations to actually create the supply app tables.

Usage:
    python manage.py fix_supply_migrations

This is safe to run multiple times - it checks if tables exist before acting.
"""

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Fix supply app migrations by removing fake records and re-running migrations'

    def handle(self, *args, **options):
        self.stdout.write("=" * 70)
        self.stdout.write(self.style.WARNING("Supply App Migration Fix"))
        self.stdout.write("=" * 70)
        self.stdout.write("")

        # Check if vendor_cards table exists
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'vendor_cards'
            """)
            vendor_cards_exists = cursor.fetchone() is not None

        if vendor_cards_exists:
            self.stdout.write(self.style.SUCCESS("✅ vendor_cards table already exists"))
            self.stdout.write("No action needed - supply app tables are properly deployed")
            return

        self.stdout.write(self.style.WARNING("⚠️  vendor_cards table does NOT exist"))
        self.stdout.write("")

        # Check django_migrations table for supply app records
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT name, applied
                FROM django_migrations
                WHERE app = 'supply'
                ORDER BY applied
            """)
            migration_records = cursor.fetchall()

        if not migration_records:
            self.stdout.write("No supply migration records found in django_migrations")
            self.stdout.write("Running migrations normally...")
            call_command('migrate', 'supply', verbosity=2)
            self.stdout.write(self.style.SUCCESS("✅ Supply migrations completed"))
            return

        self.stdout.write("Found supply migration records in django_migrations:")
        for name, applied in migration_records:
            self.stdout.write(f"  - {name} (applied: {applied})")
        self.stdout.write("")

        self.stdout.write(self.style.WARNING("These migrations are marked as applied but tables don't exist."))
        self.stdout.write("Using Django's migration system to fix this...")
        self.stdout.write("")

        # Use Django's --fake-initial approach
        # Step 1: Mark migrations as unapplied using fake flag
        self.stdout.write("Step 1: Marking supply.0001_initial as unapplied (fake)...")
        try:
            call_command('migrate', 'supply', '0001', fake=True, verbosity=0)
            self.stdout.write(self.style.SUCCESS("✅ Marked as unapplied"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to fake-unapply: {e}"))
            self.stdout.write("Trying direct database approach...")

            # Fallback: manually remove migration records
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM django_migrations WHERE app = 'supply'")
                    deleted_count = cursor.rowcount
                    self.stdout.write(self.style.SUCCESS(f"✅ Deleted {deleted_count} migration record(s)"))

        self.stdout.write("")
        self.stdout.write("Step 2: Running supply migrations to create tables...")
        self.stdout.write("")

        # Run migrations
        try:
            call_command('migrate', 'supply', verbosity=2)
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("=" * 70))
            self.stdout.write(self.style.SUCCESS("✅ Supply app tables created successfully"))
            self.stdout.write(self.style.SUCCESS("=" * 70))
        except Exception as e:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR("=" * 70))
            self.stdout.write(self.style.ERROR(f"❌ Migration failed: {e}"))
            self.stdout.write(self.style.ERROR("=" * 70))
            raise
