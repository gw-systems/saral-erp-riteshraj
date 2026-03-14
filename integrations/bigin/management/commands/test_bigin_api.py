from django.core.management.base import BaseCommand
from integrations.bigin.token_manager import get_valid_token
import requests
from django.conf import settings

class Command(BaseCommand):
    help = 'Test Bigin API directly'

    def add_arguments(self, parser):
        parser.add_argument(
            '--module',
            type=str,
            default='Deals',
            help='Module to test (Contacts, Deals, Accounts, etc.)'
        )

    def handle(self, *args, **options):
        module = options['module']
        
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"Testing Bigin API for {module}")
        self.stdout.write(f"{'='*60}\n")
        
        # Get token
        self.stdout.write("1. Getting access token...")
        try:
            token = get_valid_token()
            self.stdout.write(self.style.SUCCESS(f"   ✅ Token obtained: {token[:20]}..."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Token failed: {str(e)}"))
            return
        
        # Test API call
        self.stdout.write(f"\n2. Testing {module} API endpoint...")
        
        base = getattr(settings, "BIGIN_API_BASE", "https://bigin.zoho.com/api/v1/")
        url = f"{base}{module}"
        
        self.stdout.write(f"   URL: {url}")
        
        headers = {
            "Authorization": f"Zoho-oauthtoken {token}",
            "Content-Type": "application/json"
        }
        
        # Fields map for different modules
        fields_map = {
            'Contacts': 'Full_Name,Email,Mobile,Owner,Account_Name,Type,Status,Lead_Source,Location,Created_Time,Modified_Time',
            'Pipelines': 'Deal_Name,Stage,Owner,Account_Name,Contact_Name,Conversion_Date,Converted_Area,Created_Time,Modified_Time',
            'Accounts': 'Account_Name,Email,Phone,Owner,Industry,Website,Created_Time,Modified_Time',
            'Products': 'Product_Name,Product_Code,Unit_Price,Owner,Created_Time,Modified_Time',
            'Notes': 'Note_Title,Note_Content,Parent_Id,Owner,Created_Time,Modified_Time',
        }

        # Get fields for this module
        fields = fields_map.get(module, 'all')

        params = {
            "page": 1,
            "per_page": 5,
            #"fields": fields
        }
        
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            
            self.stdout.write(f"   Status: {resp.status_code}")
            self.stdout.write(f"   Headers: {dict(resp.headers)}")
            
            if resp.status_code == 200:
                data = resp.json()
                records = data.get("data", [])
                
                self.stdout.write(self.style.SUCCESS(f"\n   ✅ Success! Found {len(records)} records"))
                
                if records:
                    self.stdout.write("\n   Sample record keys:")
                    for key in list(records[0].keys())[:10]:
                        self.stdout.write(f"      - {key}")
                    
                    self.stdout.write(f"\n   First record:")
                    import json
                    self.stdout.write(f"      {json.dumps(records[0], indent=2)[:500]}...")
                else:
                    self.stdout.write(self.style.WARNING("   ⚠️  No records found in response"))
                    
            elif resp.status_code == 204:
                self.stdout.write(self.style.WARNING("   ⚠️  No content (module might be empty)"))
            else:
                self.stdout.write(self.style.ERROR(f"   ❌ Error: {resp.text[:200]}"))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Request failed: {str(e)}"))
            import traceback
            self.stdout.write(traceback.format_exc())
        
        self.stdout.write(f"\n{'='*60}\n")