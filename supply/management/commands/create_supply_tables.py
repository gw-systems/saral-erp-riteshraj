"""
Django management command to create supply app tables manually.

This command checks if supply tables exist, and if not, runs sqlmigrate
to get the SQL and executes it directly. This bypasses the migration
dependency issues while still using Django's migration SQL generation.

Usage:
    python manage.py create_supply_tables

This is safe to run multiple times - it checks if tables exist before acting.
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.core.management import call_command
import sys
from io import StringIO


class Command(BaseCommand):
    help = 'Create supply app tables by executing migration SQL directly'

    def handle(self, *args, **options):
        self.stdout.write("=" * 70)
        self.stdout.write(self.style.WARNING("Supply App Table Creation"))
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
        self.stdout.write("Creating supply app tables using migration SQL...")
        self.stdout.write("")

        # Get SQL for supply.0001_initial migration
        self.stdout.write("Generating SQL from supply.0001_initial migration...")
        sql_output = StringIO()
        try:
            call_command('sqlmigrate', 'supply', '0001', stdout=sql_output)
            sql = sql_output.getvalue()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to generate SQL: {e}"))
            raise

        if not sql.strip():
            self.stdout.write(self.style.ERROR("❌ No SQL generated"))
            return

        self.stdout.write(self.style.SUCCESS(f"✅ Generated {len(sql)} characters of SQL"))
        self.stdout.write("")

        # Execute the SQL
        self.stdout.write("Executing SQL to create tables...")
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql)
            self.stdout.write(self.style.SUCCESS("✅ SQL executed successfully"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ SQL execution failed: {e}"))
            raise

        self.stdout.write("")

        # Mark migrations as applied in django_migrations
        self.stdout.write("Marking supply migrations as applied...")
        with connection.cursor() as cursor:
            # Mark 0001_initial as applied
            cursor.execute("""
                INSERT INTO django_migrations (app, name, applied)
                VALUES ('supply', '0001_initial', NOW())
                ON CONFLICT DO NOTHING
            """)
            # Mark 0002 as applied (it uses ConditionalAlterField which is safe to skip)
            cursor.execute("""
                INSERT INTO django_migrations (app, name, applied)
                VALUES ('supply', '0002_citycode_created_at_citycode_is_active_and_more', NOW())
                ON CONFLICT DO NOTHING
            """)
        self.stdout.write(self.style.SUCCESS("✅ Migrations marked as applied"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(self.style.SUCCESS("✅ Supply app tables created successfully"))
        self.stdout.write(self.style.SUCCESS("=" * 70))
