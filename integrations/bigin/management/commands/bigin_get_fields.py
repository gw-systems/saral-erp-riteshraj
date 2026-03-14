from django.core.management.base import BaseCommand
from integrations.bigin.token_manager import get_valid_token
import requests
from django.conf import settings
import json

class Command(BaseCommand):
    help = 'Fetch all field metadata from Bigin for all modules'

    def add_arguments(self, parser):
        parser.add_argument(
            '--module',
            type=str,
            default='all',
            help='Module to fetch fields for (Contacts, Pipelines, Accounts, etc.) or "all"'
        )

    def handle(self, *args, **options):
        module_filter = options['module']
        
        # Get all modules first
        modules = ['Contacts', 'Pipelines', 'Accounts', 'Products', 'Notes']
        
        if module_filter != 'all':
            modules = [module_filter]
        
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write("BIGIN FIELD METADATA")
        self.stdout.write(f"{'='*80}\n")
        
        token = get_valid_token()
        base = getattr(settings, "BIGIN_API_BASE", "https://www.zohoapis.com/bigin/v2/")
        
        for module in modules:
            self.stdout.write(f"\n{'='*80}")
            self.stdout.write(f"MODULE: {module}")
            self.stdout.write(f"{'='*80}\n")
            
            url = f"{base}settings/fields?module={module}"
            headers = {"Authorization": f"Zoho-oauthtoken {token}"}
            
            try:
                resp = requests.get(url, headers=headers, timeout=30)
                
                if resp.status_code == 200:
                    data = resp.json()
                    fields = data.get('fields', [])
                    
                    self.stdout.write(f"Total fields: {len(fields)}\n")
                    
                    # Group by data type
                    date_fields = []
                    text_fields = []
                    lookup_fields = []
                    other_fields = []
                    
                    for field in fields:
                        api_name = field.get('api_name')
                        field_label = field.get('field_label')
                        data_type = field.get('data_type')
                        
                        if data_type in ['date', 'datetime']:
                            date_fields.append((api_name, field_label, data_type))
                        elif data_type == 'lookup':
                            lookup_fields.append((api_name, field_label, data_type))
                        elif data_type in ['text', 'textarea', 'email', 'phone']:
                            text_fields.append((api_name, field_label, data_type))
                        else:
                            other_fields.append((api_name, field_label, data_type))
                    
                    # Display date fields first (most important)
                    if date_fields:
                        self.stdout.write(self.style.SUCCESS("\n📅 DATE/DATETIME FIELDS:"))
                        for api_name, label, dtype in date_fields:
                            self.stdout.write(f"  • {api_name:40} | {label:30} | {dtype}")
                    
                    # Display lookup fields
                    if lookup_fields:
                        self.stdout.write(self.style.SUCCESS("\n🔗 LOOKUP FIELDS:"))
                        for api_name, label, dtype in lookup_fields:
                            self.stdout.write(f"  • {api_name:40} | {label:30} | {dtype}")
                    
                    # Display text fields
                    if text_fields:
                        self.stdout.write(self.style.SUCCESS("\n📝 TEXT FIELDS:"))
                        for api_name, label, dtype in text_fields:
                            self.stdout.write(f"  • {api_name:40} | {label:30} | {dtype}")
                    
                    # Display other fields
                    if other_fields:
                        self.stdout.write(self.style.SUCCESS("\n🔧 OTHER FIELDS:"))
                        for api_name, label, dtype in other_fields:
                            self.stdout.write(f"  • {api_name:40} | {label:30} | {dtype}")
                    
                    # Save full JSON to file
                    filename = f"bigin_fields_{module}.json"
                    with open(filename, 'w') as f:
                        json.dump(data, f, indent=2)
                    self.stdout.write(f"\n💾 Full field metadata saved to: {filename}")
                    
                else:
                    self.stdout.write(self.style.ERROR(f"❌ Error {resp.status_code}: {resp.text}"))
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Exception: {str(e)}"))
        
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write(self.style.SUCCESS("✅ Field metadata fetch complete!"))
        self.stdout.write(f"{'='*80}\n")