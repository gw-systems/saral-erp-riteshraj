import csv
from django.core.management.base import BaseCommand
from projects.models import ProjectCode


class Command(BaseCommand):
    help = 'Import operation_mode and mis_status from CSV'
    
    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to CSV file')
    
    def handle(self, *args, **options):
        csv_file = options['csv_file']
        
        operation_mode_map = {
            'Auto Mode': 'auto_mode',
            'Data Sharing': 'data_sharing',
            'Active Engagement': 'active_engagement',
        }
        
        mis_status_map = {
            'MIS Daily': 'mis_daily',
            'MIS Weekly': 'mis_weekly',
            'MIS Monthly': 'mis_monthly',
            'Inciflo': 'inciflo',
            'MIS Not Required': 'mis_not_required',
            'MIS Automode': 'mis_daily',
        }
        
        updated = 0
        skipped = 0
        
        with open(csv_file, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            for row in reader:
                code = row.get('code', '').strip()
                operation_mode_raw = row.get('operation_mode', '').strip()
                mis_status_raw = row.get('mis_status', '').strip()
                
                if not code:
                    continue
                
                try:
                    project = ProjectCode.objects.get(code=code)
                    
                    if operation_mode_raw in operation_mode_map:
                        project.operation_mode = operation_mode_map[operation_mode_raw]
                    
                    if mis_status_raw in mis_status_map:
                        project.mis_status = mis_status_map[mis_status_raw]
                    
                    project.save()
                    updated += 1
                    self.stdout.write(self.style.SUCCESS(f"✓ Updated: {code}"))
                    
                except ProjectCode.DoesNotExist:
                    skipped += 1
                    self.stdout.write(self.style.WARNING(f"✗ Not found: {code}"))
        
        self.stdout.write(self.style.SUCCESS(f"\n✅ Import Complete!"))
        self.stdout.write(f"Updated: {updated} | Skipped: {skipped}")