"""
One-time fix for missing monthly_billing columns.
Safe to run multiple times - checks if columns exist before adding.
Can be deleted after production deployment is confirmed working.
"""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Add missing columns to monthly_billings table (idempotent)'

    def handle(self, *args, **options):
        cursor = connection.cursor()
        
        # Columns added in migration 0042
        columns_to_add = [
            ('handling_in_client_variance', 'NUMERIC(15,2) NULL'),
            ('handling_in_override_reason', "TEXT NOT NULL DEFAULT ''"),
            ('handling_in_vendor_variance', 'NUMERIC(15,2) NULL'),
            ('handling_out_client_variance', 'NUMERIC(15,2) NULL'),
            ('handling_out_override_reason', "TEXT NOT NULL DEFAULT ''"),
            ('handling_out_vendor_variance', 'NUMERIC(15,2) NULL'),
            ('included_adhoc_ids', "TEXT NOT NULL DEFAULT ''"),
            ('storage_client_variance', 'NUMERIC(15,2) NULL'),
            ('storage_override_reason', "TEXT NOT NULL DEFAULT ''"),
            ('storage_vendor_variance', 'NUMERIC(15,2) NULL'),
        ]

        # Check which columns already exist
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'monthly_billings'
        """)
        existing_cols = {row[0] for row in cursor.fetchall()}
        
        added = 0
        skipped = 0
        
        self.stdout.write('Checking monthly_billings columns...')
        self.stdout.write('')
        
        for col_name, col_type in columns_to_add:
            if col_name in existing_cols:
                self.stdout.write(f'  ✓ Exists: {col_name}')
                skipped += 1
            else:
                try:
                    cursor.execute(f'ALTER TABLE monthly_billings ADD COLUMN {col_name} {col_type}')
                    self.stdout.write(self.style.SUCCESS(f'  + Added: {col_name}'))
                    added += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'  ✗ Error {col_name}: {e}'))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Done! Added: {added}, Already existed: {skipped}'))