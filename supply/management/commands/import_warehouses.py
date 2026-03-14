"""
Import warehouse data from CSV files.

Supports two dataset formats:
1. Dataset 1 (Basic): Vendor Name, Agreement dates, Location, SLA Status
2. Dataset 2 (Detailed): Complete warehouse profile with 21 columns

Usage:
    python manage.py import_warehouses <csv_file> --dataset-type=[basic|detailed]
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from supply.models import (
    VendorCard, Location, VendorWarehouse,
    WarehouseProfile, WarehouseCapacity, WarehouseCommercial,
    WarehouseContact, WarehousePhoto
)
from dropdown_master_data.models import (
    WarehouseGrade, BusinessType, PropertyType,
    SLAStatus, StorageUnit
)
from accounts.models import User
import csv
import os
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime


class Command(BaseCommand):
    help = 'Import warehouse data from CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to CSV file')
        parser.add_argument(
            '--dataset-type',
            type=str,
            choices=['basic', 'detailed'],
            default='detailed',
            help='Type of dataset: basic (8 columns) or detailed (21 columns)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Validate data without importing'
        )

    def handle(self, *args, **kwargs):
        csv_file = kwargs['csv_file']
        dataset_type = kwargs['dataset_type']
        dry_run = kwargs['dry_run']

        # Check if file exists
        if not os.path.exists(csv_file):
            self.stdout.write(self.style.ERROR(f'❌ File not found: {csv_file}'))
            return

        self.stdout.write(self.style.SUCCESS(f'📂 Reading file: {csv_file}'))
        self.stdout.write(self.style.SUCCESS(f'📊 Dataset type: {dataset_type.upper()}'))

        if dry_run:
            self.stdout.write(self.style.WARNING('⚠️  DRY RUN MODE - No changes will be saved'))

        try:
            with open(csv_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)

                # Statistics
                total_rows = 0
                success_count = 0
                error_count = 0
                skip_count = 0
                errors = []

                for row_num, row in enumerate(reader, start=2):
                    total_rows += 1

                    try:
                        if dataset_type == 'basic':
                            result = self.process_basic_row(row, row_num, dry_run)
                        else:
                            result = self.process_detailed_row(row, row_num, dry_run)

                        if result['status'] == 'success':
                            success_count += 1
                            self.stdout.write(self.style.SUCCESS(f'✅ Row {row_num}: {result["message"]}'))
                        elif result['status'] == 'skip':
                            skip_count += 1
                            self.stdout.write(self.style.WARNING(f'⏭️  Row {row_num}: {result["message"]}'))
                        else:
                            error_count += 1
                            errors.append(f'Row {row_num}: {result["message"]}')
                            self.stdout.write(self.style.ERROR(f'❌ Row {row_num}: {result["message"]}'))

                    except Exception as e:
                        error_count += 1
                        errors.append(f'Row {row_num}: Unexpected error - {str(e)}')
                        self.stdout.write(self.style.ERROR(f'❌ Row {row_num}: {str(e)}'))
                        continue

            # Final report
            self.stdout.write(self.style.SUCCESS('\n' + '='*60))
            self.stdout.write(self.style.SUCCESS('📊 IMPORT SUMMARY'))
            self.stdout.write(self.style.SUCCESS('='*60))
            self.stdout.write(f'Total rows processed: {total_rows}')
            self.stdout.write(self.style.SUCCESS(f'✅ Successful: {success_count}'))
            self.stdout.write(self.style.WARNING(f'⏭️  Skipped: {skip_count}'))
            self.stdout.write(self.style.ERROR(f'❌ Failed: {error_count}'))

            if errors:
                self.stdout.write(self.style.ERROR('\n⚠️  ERRORS:'))
                for error in errors[:30]:
                    self.stdout.write(self.style.ERROR(f'  • {error}'))
                if len(errors) > 30:
                    self.stdout.write(self.style.ERROR(f'  ... and {len(errors) - 30} more errors'))

            if dry_run:
                self.stdout.write(self.style.WARNING('\n⚠️  DRY RUN completed - No data was saved'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Fatal error: {str(e)}'))
            import traceback
            self.stdout.write(self.style.ERROR(traceback.format_exc()))

    def process_basic_row(self, row, row_num, dry_run):
        """
        Process basic dataset with columns:
        Vendor Name, Agreement Start Date, Agreement End Date,
        State, City, Location, Warehouse Address, SLA Status
        """
        # Extract fields
        vendor_name = self.clean_text(row.get('Vendor Name'))
        agreement_start = self.clean_text(row.get('Agreement Start Date'))
        agreement_end = self.clean_text(row.get('Agreement End Date'))
        state = self.clean_text(row.get('State'))
        city = self.clean_text(row.get('City'))
        location = self.clean_text(row.get('Location'))
        warehouse_address = self.clean_text(row.get('Warehouse Address'))
        sla_status = self.clean_text(row.get('SLA Status'))

        # Validation
        if not vendor_name:
            return {'status': 'error', 'message': 'Missing Vendor Name'}

        if not all([state, city]):
            return {'status': 'error', 'message': 'Missing required location fields (State, City)'}

        # If location is empty, skip (incomplete data)
        if not location:
            return {'status': 'skip', 'message': 'Missing location - incomplete data'}

        # Normalize SLA status
        sla_code = self.normalize_sla_status(sla_status)
        if not sla_code:
            return {'status': 'error', 'message': f'Invalid SLA Status: {sla_status}'}

        # Parse dates
        start_date = self.parse_date(agreement_start)
        end_date = self.parse_date(agreement_end)

        if dry_run:
            return {
                'status': 'success',
                'message': f'Would import: {vendor_name} - {state}/{city}/{location}'
            }

        try:
            with transaction.atomic():
                # Get or create VendorCard
                vendor = self.get_or_create_vendor(vendor_name)

                # Get or create Location
                loc = self.get_or_create_location(state, city, location)

                # Check if warehouse exists
                existing = VendorWarehouse.objects.filter(
                    vendor_code=vendor,
                    warehouse_location=loc
                ).first()

                if existing:
                    # Update existing
                    if warehouse_address:
                        existing.warehouse_address = warehouse_address
                    existing.save()

                    # Update commercial if dates provided
                    if start_date or end_date:
                        commercial, _ = WarehouseCommercial.objects.get_or_create(
                            warehouse=existing
                        )
                        if start_date:
                            commercial.contract_start_date = start_date
                        if end_date:
                            commercial.contract_end_date = end_date
                        commercial.sla_status_id = sla_code
                        commercial.save()

                    return {
                        'status': 'success',
                        'message': f'Updated {existing.warehouse_code}'
                    }
                else:
                    # Create new warehouse
                    warehouse = VendorWarehouse.objects.create(
                        vendor_code=vendor,
                        warehouse_location=loc,
                        warehouse_address=warehouse_address or ''
                    )

                    # Create commercial record
                    WarehouseCommercial.objects.create(
                        warehouse=warehouse,
                        sla_status_id=sla_code,
                        contract_start_date=start_date,
                        contract_end_date=end_date
                    )

                    return {
                        'status': 'success',
                        'message': f'Created {warehouse.warehouse_code}'
                    }

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def process_detailed_row(self, row, row_num, dry_run):
        """
        Process detailed dataset with 21 columns:
        Vendor Partner, Warehouse Grade, Type of Business, State, City, Area,
        Type of Property, Total Sq Ft, Available, Type, 3PL rates,
        Handling Rates /MT, Handling Rates /20 KG, Remarks, Sales Person,
        Number, Location POC, Address, Google Location, SLA, Photos
        """
        # Extract fields
        vendor_name = self.clean_text(row.get('Vendor Partner'))
        warehouse_grade = self.clean_text(row.get('Warehouse Grade'))
        business_type = self.clean_text(row.get('Type of Business'))
        state = self.clean_text(row.get('State'))
        city = self.clean_text(row.get('City'))
        area = self.clean_text(row.get('Area'))
        property_type = self.clean_text(row.get('Type of Property'))
        total_sqft = self.clean_text(row.get('Total Sq Ft'))
        available = self.clean_text(row.get('Available'))
        capacity_type = self.clean_text(row.get('Type'))
        rate_3pl = self.clean_text(row.get('3PL rates'))
        handling_mt = self.clean_text(row.get('Handling Rates /MT'))
        handling_20kg = self.clean_text(row.get('Handling Rates /20 KG'))
        remarks = self.clean_text(row.get('Remarks'))
        sales_person = self.clean_text(row.get('Sales Person'))
        phone = self.clean_text(row.get('Number'))
        location_poc = self.clean_text(row.get('Location POC'))
        address = self.clean_text(row.get('Address'))
        google_location = self.clean_text(row.get('Google Location'))
        sla_status = self.clean_text(row.get('SLA'))
        photos = self.clean_text(row.get('Photos'))

        # Validation
        if not vendor_name:
            return {'status': 'skip', 'message': 'Missing Vendor Partner - skipping empty row'}

        if not all([state, city]):
            return {'status': 'error', 'message': 'Missing required location fields (State, City)'}

        # If area is empty, skip (incomplete data)
        if not area:
            return {'status': 'skip', 'message': 'Missing Area - incomplete data'}

        # Normalize master data codes
        grade_code = self.normalize_warehouse_grade(warehouse_grade)
        business_code = self.normalize_business_type(business_type)
        property_code = self.normalize_property_type(property_type)
        sla_code = self.normalize_sla_status(sla_status)
        capacity_unit_code = self.normalize_capacity_type(capacity_type)

        # Parse numeric values
        total_sqft_val = self.parse_decimal(total_sqft)
        available_val = self.parse_decimal(available)
        rate_3pl_val = self.parse_decimal(rate_3pl)
        handling_mt_val = self.parse_decimal(handling_mt)
        handling_20kg_val = self.parse_decimal(handling_20kg)

        if dry_run:
            return {
                'status': 'success',
                'message': f'Would import: {vendor_name} - {state}/{city}/{area}'
            }

        try:
            with transaction.atomic():
                # Get or create VendorCard
                vendor = self.get_or_create_vendor(vendor_name)

                # Get or create Location
                loc = self.get_or_create_location(state, city, area)

                # Check if warehouse exists
                existing = VendorWarehouse.objects.filter(
                    vendor_code=vendor,
                    warehouse_location=loc
                ).first()

                if existing:
                    warehouse = existing
                    action = 'Updated'
                else:
                    # Create new warehouse
                    warehouse = VendorWarehouse.objects.create(
                        vendor_code=vendor,
                        warehouse_location=loc,
                        warehouse_address=address or '',
                        google_map_location=google_location or ''
                    )
                    action = 'Created'

                # Update/Create WarehouseProfile
                if grade_code or property_code or business_code or remarks:
                    profile, _ = WarehouseProfile.objects.get_or_create(
                        warehouse=warehouse
                    )
                    if grade_code:
                        profile.warehouse_grade_id = grade_code
                    if property_code:
                        profile.property_type_id = property_code
                    if business_code:
                        profile.business_type_id = business_code
                    if remarks:
                        profile.remarks = remarks
                    profile.save()

                # Update/Create WarehouseCapacity
                if total_sqft_val or available_val or capacity_unit_code:
                    capacity, _ = WarehouseCapacity.objects.get_or_create(
                        warehouse=warehouse
                    )
                    if total_sqft_val:
                        capacity.total_area_sqft = total_sqft_val
                    if available_val:
                        capacity.available_capacity = available_val
                    if capacity_unit_code:
                        capacity.capacity_unit_type_id = capacity_unit_code
                    capacity.save()

                # Update/Create WarehouseCommercial
                if sla_code or rate_3pl_val:
                    commercial, _ = WarehouseCommercial.objects.get_or_create(
                        warehouse=warehouse
                    )
                    if sla_code:
                        commercial.sla_status_id = sla_code
                    if rate_3pl_val:
                        commercial.indicative_rate = rate_3pl_val
                    commercial.save()

                # Create/Update WarehouseContact
                if location_poc or phone:
                    contact, _ = WarehouseContact.objects.get_or_create(
                        warehouse_code=warehouse,
                        defaults={
                            'warehouse_contact_person': location_poc or '',
                            'warehouse_contact_phone': phone or ''
                        }
                    )
                    if location_poc:
                        contact.warehouse_contact_person = location_poc
                    if phone:
                        contact.warehouse_contact_phone = phone
                    contact.save()

                return {
                    'status': 'success',
                    'message': f'{action} {warehouse.warehouse_code}'
                }

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def clean_text(self, value):
        """Clean and normalize text fields"""
        if value is None:
            return None
        value = str(value).strip()
        return value if value and value.lower() not in ['', 'none', 'null', 'nan'] else None

    def parse_decimal(self, value):
        """Parse decimal from various formats: '36/-', '36', '5/-', etc."""
        if not value:
            return None
        try:
            # Remove '/-' suffix and other non-numeric characters except decimal point
            cleaned = re.sub(r'[^\d.]', '', str(value))
            if cleaned:
                return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            pass
        return None

    def parse_date(self, value):
        """Parse date from various formats"""
        if not value:
            return None
        try:
            # Try common date formats
            for fmt in ['%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d', '%d-%b-%Y', '%d %b %Y']:
                try:
                    return datetime.strptime(str(value).strip(), fmt).date()
                except ValueError:
                    continue
        except:
            pass
        return None

    def normalize_warehouse_grade(self, value):
        """Convert 'Grade-B' → 'grade_b'"""
        if not value:
            return None
        value = value.lower().strip()
        if 'grade' in value:
            # Extract letter after 'grade'
            match = re.search(r'grade[- ]?([abc])', value)
            if match:
                return f'grade_{match.group(1)}'
        return None

    def normalize_business_type(self, value):
        """Convert 'B2B' → 'b2b', 'B2C' → 'b2c', etc."""
        if not value:
            return None
        value = value.lower().strip()
        if value in ['b2b', 'b2c', 'both']:
            return value
        return None

    def normalize_property_type(self, value):
        """Convert 'In Shed' → 'in_shed', etc."""
        if not value:
            return None
        value = value.lower().strip()
        mapping = {
            'in shed': 'in_shed',
            'in-shed': 'in_shed',
            'inshed': 'in_shed',
            'open': 'open',
            'covered': 'covered',
            'temperature controlled': 'temperature_controlled',
            'temp controlled': 'temperature_controlled',
        }
        return mapping.get(value)

    def normalize_sla_status(self, value):
        """Convert 'Signed' → 'signed', 'Not Signed Yet' → 'not_signed', etc."""
        if not value:
            return 'not_signed'  # Default
        value = value.lower().strip()
        if 'signed' in value and 'not' not in value:
            return 'signed'
        elif 'not' in value or 'yet' in value:
            return 'not_signed'
        elif 'negotiat' in value:
            return 'under_negotiation'
        elif 'expired' in value:
            return 'expired'
        return 'not_signed'  # Default

    def normalize_capacity_type(self, value):
        """Convert 'Sq Ft' → 'sqft', etc."""
        if not value:
            return 'sqft'  # Default
        value = value.lower().strip()
        if 'sq' in value or 'sqft' in value:
            return 'sqft'
        elif 'pallet' in value:
            return 'pallet'
        elif 'unit' in value:
            return 'unit'
        elif 'order' in value:
            return 'order'
        return 'sqft'  # Default

    def get_or_create_vendor(self, vendor_name):
        """Get or create VendorCard by vendor name"""
        # Try to find existing vendor by legal name or short name
        vendor = VendorCard.objects.filter(
            vendor_legal_name__iexact=vendor_name
        ).first()

        if not vendor:
            vendor = VendorCard.objects.filter(
                vendor_short_name__iexact=vendor_name
            ).first()

        if not vendor:
            # Create new vendor
            vendor = VendorCard.objects.create(
                vendor_legal_name=vendor_name,
                # vendor_code and vendor_short_name will be auto-generated
            )

        return vendor

    def get_or_create_location(self, state, city, location):
        """Get or create Location by state, city, location"""
        loc, created = Location.objects.get_or_create(
            state=state,
            city=city,
            location=location
        )
        return loc
