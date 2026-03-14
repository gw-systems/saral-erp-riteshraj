"""
Import projects from CSV - REPLACES entire ProjectCode table
Accepts all values as-is, including blank project_id
Usage: python manage.py import_projects --file data/imports/projects.csv
"""

import csv
from django.core.management.base import BaseCommand
from projects.models import ProjectCode


class Command(BaseCommand):
    help = 'Import projects from CSV (DELETES all existing projects first)'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, required=True, help='Path to CSV file')
        parser.add_argument('--dry-run', action='store_true', help='Preview without importing')

    def handle(self, *args, **options):
        csv_file = options['file']
        dry_run = options.get('dry_run', False)
        
        self.stdout.write("=" * 80)
        self.stdout.write(self.style.WARNING('PROJECT IMPORT - DELETE & REPLACE MODE'))
        self.stdout.write("=" * 80)
        
        # Read CSV first
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
        self.stdout.write(f'\n📊 Found {total_rows} projects in CSV')
        
        # Show what will be deleted
        existing_count = ProjectCode.objects.count()
        self.stdout.write(f'🗑️  Will delete {existing_count} existing projects')
        
        # Count blanks for info
        blank_project_ids = sum(1 for row in rows if not row.get('project_id', '').strip())
        if blank_project_ids > 0:
            self.stdout.write(f'ℹ️  Found {blank_project_ids} projects with blank project_id (will be accepted)')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n🔍 DRY RUN MODE - No changes will be made\n'))
            self.stdout.write('Preview of first 5 projects:')
            for i, row in enumerate(rows[:5], 1):
                proj_id = row.get('project_id', '').strip() or '[BLANK]'
                code = row.get('code', 'NO_CODE')
                client = row.get('client_name', 'NO_CLIENT')
                self.stdout.write(f"{i}. {code} | {proj_id} | {client}")
            self.stdout.write(f'\n... and {total_rows - 5} more projects')
            self.stdout.write(self.style.SUCCESS(f'\n✅ Dry run complete. Run without --dry-run to import.'))
            return
        
        # Confirm deletion
        self.stdout.write(self.style.WARNING(f'\n⚠️  This will DELETE all {existing_count} existing projects!'))
        confirm = input('Type "yes" to continue: ')
        if confirm.lower() != 'yes':
            self.stdout.write(self.style.ERROR('❌ Import cancelled'))
            return
        
        # DELETE ALL EXISTING PROJECTS
        self.stdout.write('\n🗑️  Deleting existing projects...')
        ProjectCode.objects.all().delete()
        self.stdout.write(self.style.SUCCESS('✅ All projects deleted'))
        
        # Import from CSV
        self.stdout.write(f'\n📥 Importing {total_rows} projects...\n')
        
        success_count = 0
        error_count = 0
        blank_count = 0
        errors = []
        
        for i, row in enumerate(rows, 1):
            try:
                # Helper function to handle blank fields
                def get_value(key):
                    value = row.get(key, '').strip()
                    return value if value else ''
                
                # Get project_id (can be blank)
                project_id = get_value('project_id')
                if not project_id:
                    blank_count += 1
                    project_id = f'BLANK_{i}'  # Temporary ID for blank rows
                
                # Create project
                ProjectCode.objects.create(
                    project_id=project_id,
                    series_type=get_value('series_type') or 'WAAS',
                    code=get_value('code') or f'CODE_{i}',
                    client_name=get_value('client_name') or '',
                    vendor_name=get_value('vendor_name') or '',
                    location=get_value('location') or '',
                    project_code=get_value('project_code') or '',
                    project_status=get_value('project_status') or 'Inactive',
                    sales_manager=get_value('sales_manager') or '',
                    operation_coordinator=get_value('operation_coordinator') or '',
                    backup_coordinator=get_value('backup_coordinator') or '',
                    state=get_value('state') or '',
                    operation_mode=get_value('operation_mode') or '',
                    mis_status=get_value('mis_status') or '',
                )
                
                success_count += 1
                
                # Progress indicator
                if i % 50 == 0:
                    self.stdout.write(f'  ... {i}/{total_rows} processed')
                
            except Exception as e:
                error_count += 1
                error_msg = f"Row {i} ({row.get('code', 'UNKNOWN')}): {str(e)}"
                errors.append(error_msg)
                self.stdout.write(self.style.ERROR(f'  ❌ {error_msg}'))
        
        # Summary
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(self.style.SUCCESS('IMPORT COMPLETE'))
        self.stdout.write('=' * 80)
        self.stdout.write(f'✅ Success: {success_count}')
        self.stdout.write(f'❌ Errors:  {error_count}')
        if blank_count > 0:
            self.stdout.write(f'ℹ️  Blank project_id: {blank_count} (saved as BLANK_N)')
        self.stdout.write(f'📊 Total:   {total_rows}')
        
        if errors:
            self.stdout.write('\n' + self.style.ERROR('Errors encountered:'))
            for error in errors[:10]:  # Show first 10 errors
                self.stdout.write(f'  - {error}')
            if len(errors) > 10:
                self.stdout.write(f'  ... and {len(errors) - 10} more errors')
        else:
            self.stdout.write(self.style.SUCCESS('\n🎉 All projects imported successfully!'))
            
        if blank_count > 0:
            self.stdout.write(self.style.WARNING(f'\n⚠️  {blank_count} projects have temporary BLANK_N IDs'))
            self.stdout.write('   Update these manually in admin panel later.')