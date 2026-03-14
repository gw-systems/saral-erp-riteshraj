"""
Import rate cards from CSV - OVERWRITES existing rate cards
ONLY imports WAAS series projects (skips GW and SAAS)
Usage: python manage.py import_projectcards --file data/imports/ratecard.csv --user-id 1
"""

import csv
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from projects.models import ProjectCode
from operations.models_projectcard import ProjectCard, StorageRate
from datetime import datetime
from decimal import Decimal, InvalidOperation

User = get_user_model()


class Command(BaseCommand):
    help = 'Import project cards from CSV - WAAS projects only (OVERWRITES existing)'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, required=True, help='Path to CSV file')
        parser.add_argument('--user-id', type=int, required=True, help='Admin user ID for created_by')
        parser.add_argument('--dry-run', action='store_true', help='Preview without importing')

    def handle(self, *args, **options):
        csv_file = options['file']
        user_id = options['user_id']
        dry_run = options.get('dry_run', False)
        
        self.stdout.write("=" * 80)
        self.stdout.write(self.style.WARNING('RATE CARD IMPORT - WAAS ONLY - OVERWRITE MODE'))
        self.stdout.write("=" * 80)
        
        # Verify user exists
        try:
            admin_user = User.objects.get(id=user_id)
            self.stdout.write(f'✅ Using admin user: {admin_user.get_full_name()} ({admin_user.email})')
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ User with ID {user_id} not found'))
            return
        
        # Read CSV
        try:
            with open(csv_file, 'r', encoding='utf-8-sig') as file:
                reader = csv.DictReader(file)
                rows = list(reader)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'❌ File not found: {csv_file}'))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error reading CSV: {str(e)}'))
            return
        
        total_rows = len(rows)
        self.stdout.write(f'\n📊 Found {total_rows} rows in CSV\n')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be made\n'))
            self.preview_import(rows)
            return
        
        # Confirm import
        self.stdout.write(self.style.WARNING('⚠️  This will DELETE existing WAAS rate cards and create new ones'))
        confirm = input('Type "yes" to continue: ')
        if confirm.lower() != 'yes':
            self.stdout.write(self.style.ERROR('❌ Import cancelled'))
            return
        
        # Import rate cards
        self.stdout.write('\n📥 Importing rate cards...\n')
        
        created_count = 0
        updated_count = 0
        skipped_empty = 0
        skipped_no_project = 0
        skipped_non_waas = 0
        error_count = 0
        errors = []
        
        for i, row in enumerate(rows, 1):
            code = row.get('Code', '').strip()
            
            if not code:
                skipped_empty += 1
                continue
            
            try:
                # Check if row has any data (other than code)
                has_data = self.row_has_data(row)
                
                if not has_data:
                    skipped_empty += 1
                    if i % 50 == 0:
                        self.stdout.write(f'  ... {i}/{total_rows} processed')
                    continue
                
                # Find project
                try:
                    project = ProjectCode.objects.get(code=code)
                except ProjectCode.DoesNotExist:
                    skipped_no_project += 1
                    errors.append(f"Row {i} ({code}): Project not found")
                    continue
                
                # Skip non-WAAS projects (GW and SAAS don't have rate cards)
                if project.series_type != 'WAAS':
                    skipped_non_waas += 1
                    if i % 50 == 0:
                        self.stdout.write(f'  ... {i}/{total_rows} processed')
                    continue
                
                # Use transaction for atomic operation
                with transaction.atomic():
                    # Delete existing rate cards for this project
                    existing_count = ProjectCard.objects.filter(project=project).count()
                    if existing_count > 0:
                        ProjectCard.objects.filter(project=project).delete()
                        updated_count += 1
                    else:
                        created_count += 1
                    
                    # Parse dates
                    agreement_start = self.parse_date(row.get('Agreement Start Date', ''))
                    agreement_end = self.parse_date(row.get('Agreement End Date', ''))
                    yearly_escalation = self.parse_date(row.get('Yearly Escalation Date', ''))
                    billing_start = self.parse_date(row.get('Billing Start Date', ''))
                    operation_start = self.parse_date(row.get('Operation Start Date', ''))
                    
                    # Parse escalation
                    escalation_value = row.get('Annual Escalation %', '').strip()
                    has_fixed_escalation, escalation_percent = self.parse_escalation(escalation_value)
                    
                    # Parse security deposit
                    security_deposit = self.parse_decimal(row.get('Security Deposit', '')) or Decimal('0.00')
                    
                    # Create ProjectCard (all fields optional except created_by)
                    project_card = ProjectCard.objects.create(
                        project=project,
                        agreement_start_date=agreement_start,
                        agreement_end_date=agreement_end,
                        yearly_escalation_date=yearly_escalation,
                        billing_start_date=billing_start,
                        operation_start_date=operation_start,
                        has_fixed_escalation=has_fixed_escalation if has_fixed_escalation is not None else True,
                        annual_escalation_percent=escalation_percent,
                        security_deposit=security_deposit,
                        created_by=admin_user,
                    )
                    
                    # Create Client Storage Rate (if has data)
                    client_min_area = self.parse_decimal(row.get('Client Minimum Billable Area', ''))
                    if client_min_area:
                        StorageRate.objects.create(
                            project_card=project_card,
                            rate_for='client',
                            space_type=self.map_space_type(row.get('Client Type', '')),
                            minimum_billable_area=client_min_area,
                            flat_rate_per_unit=self.parse_decimal(row.get('Client Rate', '')),
                            monthly_billable_amount=self.parse_decimal(row.get('Client Monthly Billable Amount', '')),
                            saas_monthly_charge=self.parse_decimal(row.get('SAAS', '')),
                        )
                    
                    # Create Vendor Storage Rate (if has data)
                    vendor_min_area = self.parse_decimal(row.get('Vendor Minimum Billable Area', ''))
                    if vendor_min_area:
                        StorageRate.objects.create(
                            project_card=project_card,
                            rate_for='vendor',
                            space_type=self.map_space_type(row.get('Vendor Type', '')),
                            minimum_billable_area=vendor_min_area,
                            flat_rate_per_unit=self.parse_decimal(row.get('Vendor Rate', '')),
                            monthly_billable_amount=self.parse_decimal(row.get('Vendor Monthly Billable Amount', '')),
                        )
                
                # Progress indicator
                if i % 50 == 0:
                    self.stdout.write(f'  ... {i}/{total_rows} processed')
                
            except Exception as e:
                error_count += 1
                error_msg = f"Row {i} ({code}): {str(e)}"
                errors.append(error_msg)
                self.stdout.write(self.style.ERROR(f'  ❌ {error_msg}'))
        
        # Summary
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(self.style.SUCCESS('IMPORT COMPLETE'))
        self.stdout.write('=' * 80)
        self.stdout.write(f'✅ Created (new):      {created_count}')
        self.stdout.write(f'🔄 Updated (replaced): {updated_count}')
        self.stdout.write(f'⏭️  Skipped (empty):    {skipped_empty}')
        self.stdout.write(f'⏭️  Skipped (GW/SAAS):  {skipped_non_waas}')
        self.stdout.write(f'⚠️  No project found:   {skipped_no_project}')
        self.stdout.write(f'❌ Errors:             {error_count}')
        self.stdout.write(f'📊 Total rows:         {total_rows}')
        
        if errors:
            self.stdout.write('\n' + self.style.ERROR('Errors encountered:'))
            for error in errors[:10]:
                self.stdout.write(f'  - {error}')
            if len(errors) > 10:
                self.stdout.write(f'  ... and {len(errors) - 10} more errors')
        
        total_success = created_count + updated_count
        if total_success > 0:
            self.stdout.write(self.style.SUCCESS(f'\n🎉 {total_success} WAAS rate cards imported successfully!'))
    
    def preview_import(self, rows):
        """Show preview of what will be imported (WAAS only)"""
        self.stdout.write('Preview of first 5 WAAS rate cards:\n')
        
        count = 0
        for i, row in enumerate(rows, 1):
            code = row.get('Code', '').strip()
            if not code or not self.row_has_data(row):
                continue
            
            # Skip non-WAAS projects
            try:
                project = ProjectCode.objects.get(code=code)
                if project.series_type != 'WAAS':
                    continue
            except ProjectCode.DoesNotExist:
                continue
            
            count += 1
            if count > 5:
                break
            
            agreement_start = row.get('Agreement Start Date', '').strip()
            client_rate = row.get('Client Rate', '').strip()
            vendor_rate = row.get('Vendor Rate', '').strip()
            
            self.stdout.write(f"{count}. {code}")
            self.stdout.write(f"   Agreement Start: {agreement_start or '[blank]'}")
            self.stdout.write(f"   Client Rate: {client_rate or '[blank]'}")
            self.stdout.write(f"   Vendor Rate: {vendor_rate or '[blank]'}")
            self.stdout.write("")
        
        # Count only WAAS projects with data
        waas_count = 0
        for row in rows:
            code = row.get('Code', '').strip()
            if code and self.row_has_data(row):
                try:
                    project = ProjectCode.objects.get(code=code)
                    if project.series_type == 'WAAS':
                        waas_count += 1
                except ProjectCode.DoesNotExist:
                    pass
        
        remaining = waas_count - 5 if waas_count > 5 else 0
        if remaining > 0:
            self.stdout.write(f'... and {remaining} more WAAS rate cards with data')
        
        self.stdout.write(f'\n✅ Total WAAS projects to import: {waas_count}')
        self.stdout.write(f'✅ Dry run complete. Run without --dry-run to import.')
    
    def row_has_data(self, row):
        """Check if row has any data other than Code"""
        exclude_fields = ['Code']
        for key, value in row.items():
            if key not in exclude_fields and value and str(value).strip():
                return True
        return False
    
    def parse_date(self, date_str):
        """Parse date from DD/MMM/YYYY or DD-MMM-YYYY format to YYYY-MM-DD"""
        if not date_str or not str(date_str).strip():
            return None
        
        date_str = str(date_str).strip()
        
        # Try different formats
        formats = [
            '%d/%b/%Y',   # 22/Nov/2024
            '%d-%b-%Y',   # 22-Nov-2024
            '%d/%B/%Y',   # 22/November/2024
            '%d-%B-%Y',   # 22-November-2024
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        return None
    
    def parse_decimal(self, value):
        """Parse decimal value, return None if empty or invalid"""
        if not value or not str(value).strip():
            return None
        
        try:
            # Remove commas and convert
            cleaned = str(value).strip().replace(',', '')
            return Decimal(cleaned)
        except (ValueError, InvalidOperation):
            return None
    
    def parse_escalation(self, value):
        """
        Parse escalation field - returns (has_fixed, percent)
        
        Returns:
            (True, 5.0) for "5"
            (False, None) for "Mutually Agreed"
            (None, None) for blank
        """
        if not value or not str(value).strip():
            return (None, None)
        
        value = str(value).strip()
        
        # Check if it's "Mutually Agreed"
        if value.lower() in ['mutually agreed', 'mutually', 'mutual']:
            return (False, None)
        
        # Try to parse as number
        try:
            percent = Decimal(value)
            return (True, percent)
        except (ValueError, InvalidOperation):
            # Unknown value, treat as blank
            return (None, None)
    
    def map_space_type(self, value):
        """Map CSV space type to model choice"""
        if not value:
            return 'sqft'  # Default
        
        value = str(value).strip().lower()
        
        if 'sq' in value or 'ft' in value or 'feet' in value:
            return 'sqft'
        elif 'pallet' in value:
            return 'pallet'
        elif 'lump' in value:
            return 'lumpsum'
        else:
            return 'sqft'  # Default fallback