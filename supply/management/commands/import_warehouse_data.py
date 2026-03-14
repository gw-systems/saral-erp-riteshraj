"""
Management command to import warehouse data from CSV/Excel file.

Usage:
    python manage.py import_warehouse_data <file_path>

Example:
    python manage.py import_warehouse_data warehouse_data.csv
    python manage.py import_warehouse_data warehouse_data.xlsx
"""

import csv
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from supply.models import (
    VendorCard, VendorWarehouse, Location,
    WarehouseProfile, WarehouseCapacity, WarehouseCommercial
)
from dropdown_master_data.models import (
    WarehouseGrade, PropertyType, BusinessType, StorageUnit
)


class Command(BaseCommand):
    help = 'Import warehouse data from CSV or Excel file'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to the CSV/Excel file')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without actually importing (preview only)'
        )

    def handle(self, *args, **options):
        file_path = options['file_path']
        dry_run = options.get('dry_run', False)

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No data will be imported'))

        try:
            if file_path.endswith('.xlsx') or file_path.endswith('.xls'):
                self.import_from_excel(file_path, dry_run)
            elif file_path.endswith('.csv'):
                self.import_from_csv(file_path, dry_run)
            else:
                raise CommandError('File must be CSV or Excel (.csv, .xlsx, .xls)')
        except FileNotFoundError:
            raise CommandError(f'File not found: {file_path}')
        except Exception as e:
            raise CommandError(f'Error importing data: {str(e)}')

    def import_from_excel(self, file_path, dry_run):
        """Import from Excel file"""
        try:
            import openpyxl
        except ImportError:
            raise CommandError('openpyxl is required for Excel files. Install it with: pip install openpyxl')

        workbook = openpyxl.load_workbook(file_path)
        sheet = workbook.active

        # Get headers from first row
        headers = [cell.value for cell in sheet[1]]

        rows = []
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not any(row):  # Skip empty rows
                continue
            row_dict = dict(zip(headers, row))
            rows.append(row_dict)

        self.process_rows(rows, dry_run)

    def import_from_csv(self, file_path, dry_run):
        """Import from CSV file"""
        with open(file_path, 'r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)

        self.process_rows(rows, dry_run)

    def process_rows(self, rows, dry_run):
        """Process and import rows"""
        self.stdout.write(f'\nProcessing {len(rows)} rows...\n')

        created_vendors = 0
        created_warehouses = 0
        skipped = 0

        with transaction.atomic():
            for idx, row in enumerate(rows, start=1):
                try:
                    result = self.process_row(row, dry_run)
                    if result['created_vendor']:
                        created_vendors += 1
                    if result['created_warehouse']:
                        created_warehouses += 1
                    if result['skipped']:
                        skipped += 1

                    self.stdout.write(
                        self.style.SUCCESS(f"✓ Row {idx}: {result['message']}")
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"✗ Row {idx}: Error - {str(e)}")
                    )
                    skipped += 1

            if dry_run:
                self.stdout.write(self.style.WARNING('\nDRY RUN - Rolling back transaction'))
                transaction.set_rollback(True)

        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS(f'Vendors created: {created_vendors}'))
        self.stdout.write(self.style.SUCCESS(f'Warehouses created: {created_warehouses}'))
        if skipped > 0:
            self.stdout.write(self.style.WARNING(f'Rows skipped: {skipped}'))
        self.stdout.write('='*60 + '\n')

    def process_row(self, row, dry_run):
        """Process a single row of data"""
        vendor_name = str(row.get('Vendor Name') or '').strip()
        if not vendor_name:
            return {'created_vendor': False, 'created_warehouse': False, 'skipped': True,
                    'message': 'Skipped - No vendor name'}

        # Get or create vendor
        vendor = self.get_or_create_vendor(vendor_name, dry_run)

        # Get or create location
        state = str(row.get('State') or '').strip()
        city = str(row.get('City') or '').strip()
        area = str(row.get('Area') or '').strip()

        if not (state and city and area):
            return {'created_vendor': bool(vendor), 'created_warehouse': False, 'skipped': True,
                    'message': f'Skipped - Missing location data for {vendor_name}'}

        location = self.get_or_create_location(state, city, area, dry_run)

        # Create warehouse
        warehouse_created = False
        if not dry_run:
            # Check if warehouse already exists
            existing_warehouse = VendorWarehouse.objects.filter(
                vendor_code=vendor,
                warehouse_location_id=location
            ).first()

            if existing_warehouse:
                warehouse = existing_warehouse
            else:
                address = str(row.get('Address') or '').strip()
                warehouse = VendorWarehouse.objects.create(
                    vendor_code=vendor,
                    warehouse_location_id=location,
                    warehouse_address=address if address else None,
                    warehouse_name=f"{vendor_name} - {area}"
                )
                warehouse_created = True

                # Create related records
                self.create_warehouse_profile(warehouse, row)
                self.create_warehouse_capacity(warehouse, row)
                self.create_warehouse_commercial(warehouse, row)

        return {
            'created_vendor': False,  # Vendor was get_or_create
            'created_warehouse': warehouse_created,
            'skipped': False,
            'message': f"{'Created' if warehouse_created else 'Found'} warehouse for {vendor_name} in {area}, {city}"
        }

    def get_or_create_vendor(self, vendor_name, dry_run):
        """Get or create vendor"""
        if dry_run:
            return VendorCard(vendor_legal_name=vendor_name)

        # Generate vendor code
        vendor_code = VendorCard.generate_vendor_code(vendor_name)

        vendor, created = VendorCard.objects.get_or_create(
            vendor_code=vendor_code,
            defaults={
                'vendor_legal_name': vendor_name,
                'vendor_short_name': ' '.join(vendor_name.split()[:2])
            }
        )
        return vendor

    def get_or_create_location(self, state, city, area, dry_run):
        """Get or create location"""
        if dry_run:
            return Location(state=state, city=city, location=area)

        location, created = Location.objects.get_or_create(
            state=state,
            city=city,
            location=area,
            defaults={'is_active': True}
        )
        return location

    def create_warehouse_profile(self, warehouse, row):
        """Create warehouse profile"""
        warehouse_grade = str(row.get('Warehouse Grade') or '').strip()
        business_type = str(row.get('Type of Business') or '').strip()
        property_type = str(row.get('Type of Property') or '').strip()

        # Get foreign key objects
        grade_obj = None
        if warehouse_grade:
            grade_obj = WarehouseGrade.objects.filter(name__icontains=warehouse_grade).first()

        business_obj = None
        if business_type:
            business_obj = BusinessType.objects.filter(name__icontains=business_type).first()

        property_obj = None
        if property_type:
            property_obj = PropertyType.objects.filter(name__icontains=property_type).first()

        WarehouseProfile.objects.create(
            warehouse=warehouse,
            warehouse_grade=grade_obj,
            business_type=business_obj,
            property_type=property_obj
        )

    def create_warehouse_capacity(self, warehouse, row):
        """Create warehouse capacity"""
        total_sqft_str = str(row.get('Total Sq Ft') or '').strip()
        available_str = str(row.get('Available') or '').strip()
        capacity_type = str(row.get('Type') or '').strip()

        # Convert to integers, handling empty/non-numeric values
        try:
            total_sqft = int(float(total_sqft_str)) if total_sqft_str and total_sqft_str != 'nan' else None
        except (ValueError, TypeError):
            total_sqft = None

        try:
            available = int(float(available_str)) if available_str and available_str != 'nan' else None
        except (ValueError, TypeError):
            available = None

        # Get storage unit type
        unit_type_obj = None
        if capacity_type:
            unit_type_obj = StorageUnit.objects.filter(name__icontains=capacity_type).first()

        WarehouseCapacity.objects.create(
            warehouse=warehouse,
            total_area_sqft=total_sqft,
            available_capacity=available,
            capacity_unit_type=unit_type_obj
        )

    def create_warehouse_commercial(self, warehouse, row):
        """Create warehouse commercial details"""
        # Parse dates
        start_date = self.parse_date(row.get('Agreement Start Date'))
        end_date = self.parse_date(row.get('Agreement End Date'))

        # Parse rates
        rates_3pl = str(row.get('3PL rates') or '').strip()
        handling_mt = str(row.get('Handling Rates /MT') or '').strip()
        handling_20kg = str(row.get('Handling Rates /20 KG') or '').strip()

        # Build remarks
        remarks_parts = []
        if rates_3pl:
            remarks_parts.append(f"3PL Rates: {rates_3pl}")
        if handling_mt:
            remarks_parts.append(f"Handling Rate (MT): {handling_mt}")
        if handling_20kg:
            remarks_parts.append(f"Handling Rate (20KG): {handling_20kg}")

        WarehouseCommercial.objects.create(
            warehouse=warehouse,
            contract_start_date=start_date,
            contract_end_date=end_date,
            remarks='\n'.join(remarks_parts) if remarks_parts else ''
        )

    def parse_date(self, date_value):
        """Parse date from various formats"""
        if not date_value or str(date_value).strip() in ['', 'nan', 'None']:
            return None

        date_str = str(date_value).strip()

        # Try different date formats
        formats = [
            '%d-%b-%Y',  # 25-Aug-2025
            '%d-%B-%Y',  # 25-August-2025
            '%Y-%m-%d',  # 2025-08-25
            '%d/%m/%Y',  # 25/08/2025
            '%m/%d/%Y',  # 08/25/2025
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        return None
