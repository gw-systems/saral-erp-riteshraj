from django.core.management.base import BaseCommand
from dropdown_master_data.models import Region, StateCode, CityCode


REGIONS = [
    ('north', 'North', 1),
    ('south', 'South', 2),
    ('east', 'East', 3),
    ('west', 'West', 4),
    ('central', 'Central', 5),
]

STATE_CODES = [
    ('Andhra Pradesh', 'AP', 1),
    ('Arunachal Pradesh', 'AR', 2),
    ('Assam', 'AS', 3),
    ('Bihar', 'BR', 4),
    ('Chhattisgarh', 'CT', 5),
    ('Goa', 'GA', 6),
    ('Gujarat', 'GJ', 7),
    ('Haryana', 'HR', 8),
    ('Himachal Pradesh', 'HP', 9),
    ('Jharkhand', 'JH', 10),
    ('Karnataka', 'KA', 11),
    ('Kerala', 'KL', 12),
    ('Madhya Pradesh', 'MP', 13),
    ('Maharashtra', 'MH', 14),
    ('Manipur', 'MN', 15),
    ('Meghalaya', 'ML', 16),
    ('Mizoram', 'MZ', 17),
    ('Nagaland', 'NL', 18),
    ('Odisha', 'OR', 19),
    ('Punjab', 'PB', 20),
    ('Rajasthan', 'RJ', 21),
    ('Sikkim', 'SK', 22),
    ('Tamil Nadu', 'TN', 23),
    ('Telangana', 'TG', 24),
    ('Tripura', 'TR', 25),
    ('Uttar Pradesh', 'UP', 26),
    ('Uttarakhand', 'UK', 27),
    ('West Bengal', 'WB', 28),
    ('Delhi', 'DL', 29),
    ('Chandigarh', 'CH', 30),
]

# Major cities for top states
MAJOR_CITIES = {
    'MH': [  # Maharashtra
        ('Mumbai', 'MUM', 1),
        ('Pune', 'PUN', 2),
        ('Nagpur', 'NAG', 3),
        ('Nashik', 'NSK', 4),
        ('Thane', 'THA', 5),
        ('Navi Mumbai', 'NMU', 6),
        ('Aurangabad', 'IXU', 7),
        ('Solapur', 'SSE', 8),
        ('Kolhapur', 'KOP', 9),
        ('Panvel', 'PNV', 10),
        ('Nhava Sheva', 'NHS', 11),
    ],
    'DL': [  # Delhi
        ('Delhi', 'DEL', 1),
        ('New Delhi', 'NDL', 2),
        ('Dwarka', 'DWK', 3),
        ('Alipur', 'ALR', 4),
    ],
    'KA': [  # Karnataka
        ('Bangalore', 'BLR', 1),
        ('Bengaluru', 'BLR', 1),
        ('Mysore', 'MYS', 2),
        ('Mangalore', 'MNG', 3),
        ('Hubli', 'HUB', 4),
    ],
    'TN': [  # Tamil Nadu
        ('Chennai', 'CHE', 1),
        ('Coimbatore', 'COI', 2),
        ('Madurai', 'MDU', 3),
        ('Tiruchirappalli', 'TRZ', 4),
        ('Salem', 'SXV', 5),
    ],
    'GJ': [  # Gujarat
        ('Ahmedabad', 'AMD', 1),
        ('Surat', 'SUR', 2),
        ('Vadodara', 'VAD', 3),
        ('Rajkot', 'RAJ', 4),
        ('Gandhinagar', 'GAN', 5),
    ],
    'HR': [  # Haryana
        ('Gurgaon', 'GGN', 1),
        ('Gurugram', 'GGN', 1),
        ('Faridabad', 'FBD', 2),
        ('Chandigarh', 'CHD', 3),
        ('Panipat', 'PAN', 4),
    ],
    'UP': [  # Uttar Pradesh
        ('Lucknow', 'LKO', 1),
        ('Kanpur', 'KAN', 2),
        ('Ghaziabad', 'GZB', 3),
        ('Agra', 'AGR', 4),
        ('Noida', 'NOI', 5),
        ('Greater Noida', 'GNO', 6),
    ],
    'WB': [  # West Bengal
        ('Kolkata', 'KOL', 1),
        ('Howrah', 'HOW', 2),
        ('Siliguri', 'SIL', 3),
    ],
    'TG': [  # Telangana
        ('Hyderabad', 'HYD', 1),
        ('Secunderabad', 'SEC', 2),
    ],
    'RJ': [  # Rajasthan
        ('Jaipur', 'JAI', 1),
        ('Jodhpur', 'JOD', 2),
        ('Udaipur', 'UDR', 3),
    ],
    'PB': [  # Punjab
        ('Ludhiana', 'LDH', 1),
        ('Amritsar', 'ATQ', 2),
        ('Chandigarh', 'CHD', 3),
    ],
}


class Command(BaseCommand):
    help = 'Populate regions, state codes, and major city codes'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('Starting geographic data population...'))
        
        # Populate Regions
        self.stdout.write('\n📍 Populating regions...')
        for code, label, order in REGIONS:
            region, created = Region.objects.get_or_create(
                code=code,
                defaults={'label': label, 'display_order': order, 'is_active': True}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  ✓ Created: {label}'))
            else:
                self.stdout.write(f'  - Already exists: {label}')
        
        # Populate State Codes
        self.stdout.write('\n🗺️  Populating state codes...')
        created_count = 0
        for state_name, state_code, order in STATE_CODES:
            state, created = StateCode.objects.get_or_create(
                state_code=state_code,
                defaults={'state_name': state_name, 'display_order': order, 'is_active': True}
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'  ✓ Created: {state_name} ({state_code})'))
            else:
                self.stdout.write(f'  - Already exists: {state_name} ({state_code})')
        
        self.stdout.write(self.style.SUCCESS(f'\n  Total states created: {created_count}/{len(STATE_CODES)}'))
        
        # Populate Major City Codes
        self.stdout.write('\n🏙️  Populating major city codes...')
        total_cities = 0
        created_cities = 0
        
        for state_code, cities in MAJOR_CITIES.items():
            self.stdout.write(f'\n  State: {state_code}')
            for city_name, city_code, order in cities:
                total_cities += 1
                city, created = CityCode.objects.get_or_create(
                    state_code_id=state_code,
                    city_code=city_code,
                    defaults={'city_name': city_name, 'display_order': order, 'is_active': True}
                )
                if created:
                    created_cities += 1
                    self.stdout.write(self.style.SUCCESS(f'    ✓ Created: {city_name} ({city_code})'))
                else:
                    # Update city_name if it already exists (for duplicates like Bangalore/Bengaluru)
                    if city.city_name != city_name:
                        self.stdout.write(f'    - Already exists: {city.city_name} ({city_code})')
                    else:
                        self.stdout.write(f'    - Already exists: {city_name} ({city_code})')
        
        self.stdout.write(self.style.SUCCESS(f'\n  Total cities created: {created_cities}/{total_cities}'))
        
        # Summary
        self.stdout.write(self.style.MIGRATE_HEADING('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('✓ Geographic data population completed!'))
        self.stdout.write(self.style.MIGRATE_HEADING('='*60))
        self.stdout.write(f'\n  Regions: {Region.objects.count()}')
        self.stdout.write(f'  States: {StateCode.objects.count()}')
        self.stdout.write(f'  Cities: {CityCode.objects.count()}')
        self.stdout.write(self.style.WARNING('\n💡 Admins can add more cities from Django Admin'))
        self.stdout.write(self.style.WARNING('   URL: /admin/dropdown_master_data/citycode/add/\n'))