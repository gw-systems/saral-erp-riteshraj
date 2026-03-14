from django.core.management.base import BaseCommand
from django.utils import timezone
from projects.models import ProjectCode
from accounts.models import User
import openpyxl
import os


class Command(BaseCommand):
    help = 'Import projects from Excel file'

    def add_arguments(self, parser):
        parser.add_argument('excel_file', type=str, help='Path to Excel file')

    def handle(self, *args, **kwargs):
        excel_file = kwargs['excel_file']
        
        # Check if file exists
        if not os.path.exists(excel_file):
            self.stdout.write(self.style.ERROR(f'❌ File not found: {excel_file}'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'📂 Reading file: {excel_file}'))
        
        try:
            # Load Excel
            wb = openpyxl.load_workbook(excel_file)
            sheet = wb.active
            
            # Statistics
            total_rows = 0
            success_count = 0
            error_count = 0
            errors = []
            
            # Get current year for project_id generation
            current_year = timezone.now().year
            year_suffix = str(current_year)[-2:]
            
            # Process each row (skip header)
            for row_num, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                total_rows += 1
                
                try:
                    # Extract columns
                    series_type = str(row[0]).strip() if row[0] else None
                    code = str(row[1]).strip() if row[1] else None
                    client_name = str(row[2]).strip() if row[2] else None
                    vendor_name = str(row[3]).strip() if row[3] else None
                    location = str(row[4]).strip() if row[4] else None
                    project_code = str(row[5]).strip() if row[5] else None
                    project_status = str(row[6]).strip() if row[6] else None
                    sales_manager_name = str(row[7]).strip() if row[7] else None
                    
                    # Validation: Check required fields
                    if not all([series_type, code, client_name, vendor_name, location, project_code, project_status]):
                        errors.append(f'Row {row_num}: Missing required fields')
                        error_count += 1
                        continue
                    
                    # Validate series_type
                    if series_type not in ['WAAS', 'SAAS', 'GW']:
                        errors.append(f'Row {row_num}: Invalid series_type "{series_type}". Must be WAAS, SAAS, or GW')
                        error_count += 1
                        continue
                    
                    # Validate project_status
                    valid_statuses = ['Active', 'Operation Not Started', 'Notice Period', 'Inactive']
                    if project_status not in valid_statuses:
                        errors.append(f'Row {row_num}: Invalid project_status "{project_status}". Must be one of: {", ".join(valid_statuses)}')
                        error_count += 1
                        continue
                    
                    # Check if code already exists
                    if ProjectCode.objects.filter(code=code).exists():
                        errors.append(f'Row {row_num}: Code "{code}" already exists in database')
                        error_count += 1
                        continue
                    
                    # Check if project_code already exists
                    if ProjectCode.objects.filter(project_code=project_code).exists():
                        errors.append(f'Row {row_num}: Project code "{project_code}" already exists in database')
                        error_count += 1
                        continue
                    
                    # Match sales_manager with User
                    sales_manager_validated = None
                    if sales_manager_name:
                        try:
                            # Try to find user by full name match
                            user = User.objects.filter(
                                is_active=True
                            ).filter(
                                first_name__iexact=sales_manager_name.split()[0] if ' ' in sales_manager_name else sales_manager_name
                            ).first()
                            
                            if user:
                                sales_manager_validated = user.get_full_name()
                            else:
                                errors.append(f'Row {row_num}: Sales manager "{sales_manager_name}" not found in system')
                                error_count += 1
                                continue
                        except Exception as e:
                            errors.append(f'Row {row_num}: Error matching sales manager: {str(e)}')
                            error_count += 1
                            continue
                    
                    # Generate project_id (auto-increment sequence)
                    # Get max sequence for this series and year
                    existing_projects = ProjectCode.objects.filter(
                        series_type=series_type,
                        project_id__startswith=f'{series_type}-{year_suffix}-'
                    )
                    
                    if existing_projects.exists():
                        # Extract sequence numbers
                        sequences = []
                        for proj in existing_projects:
                            try:
                                seq = int(proj.project_id.split('-')[-1])
                                sequences.append(seq)
                            except:
                                continue
                        next_seq = max(sequences) + 1 if sequences else 1
                    else:
                        next_seq = 1
                    
                    project_id = f"{series_type}-{year_suffix}-{next_seq:03d}"
                    
                    # Create project
                    ProjectCode.objects.create(
                        project_id=project_id,
                        series_type=series_type,
                        code=code,
                        project_code=project_code,
                        client_name=client_name,
                        vendor_name=vendor_name,
                        location=location,
                        state=None,  # Leave blank as requested
                        project_status=project_status,
                        sales_manager=sales_manager_validated,
                        billing_start_date=None,  # Leave blank as requested
                        created_at=timezone.now(),
                        updated_at=timezone.now()
                    )
                    
                    success_count += 1
                    self.stdout.write(self.style.SUCCESS(f'✅ Row {row_num}: Created {project_id} - {code}'))
                    
                except Exception as e:
                    errors.append(f'Row {row_num}: {str(e)}')
                    error_count += 1
                    continue
            
            # Final report
            self.stdout.write(self.style.SUCCESS('\n' + '='*60))
            self.stdout.write(self.style.SUCCESS('📊 IMPORT SUMMARY'))
            self.stdout.write(self.style.SUCCESS('='*60))
            self.stdout.write(f'Total rows processed: {total_rows}')
            self.stdout.write(self.style.SUCCESS(f'✅ Successful: {success_count}'))
            self.stdout.write(self.style.ERROR(f'❌ Failed: {error_count}'))
            
            if errors:
                self.stdout.write(self.style.ERROR('\n⚠️  ERRORS:'))
                for error in errors[:20]:  # Show first 20 errors
                    self.stdout.write(self.style.ERROR(f'  • {error}'))
                if len(errors) > 20:
                    self.stdout.write(self.style.ERROR(f'  ... and {len(errors) - 20} more errors'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Fatal error: {str(e)}'))