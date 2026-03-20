"""
Django management command to export all courier rate cards from database to master_card.json.

Usage:
    python manage.py export_master_card
    python manage.py export_master_card --verbose
"""
import json
from pathlib import Path
from django.core.management.base import BaseCommand
from ...models import Courier


FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"


class Command(BaseCommand):
    help = 'Export all courier rate cards from database to master_card.json'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Display detailed information about each exported carrier',
        )

    def handle(self, *args, **options):
        verbose = options.get('verbose', False)
        
        # Define output path
        output_path = FIXTURES_DIR / "master_card.json"
        
        self.stdout.write(self.style.MIGRATE_HEADING('Exporting courier data to master_card.json...'))
        self.stdout.write(f'Output path: {output_path}\n')
        
        try:
            # Query all couriers (both active and inactive)
            couriers = Courier.objects.all().order_by('name')
            
            if not couriers.exists():
                self.stdout.write(self.style.WARNING('No couriers found in database!'))
                return
            
            # Extract rate cards
            rate_cards = []
            for courier in couriers:
                rate_card = courier.rate_card
                
                # Ensure rate_card is a dict
                if not isinstance(rate_card, dict):
                    self.stdout.write(
                        self.style.WARNING(
                            f'  ⚠ Skipping {courier.name} - invalid rate_card format'
                        )
                    )
                    continue
                
                rate_cards.append(rate_card)
                
                if verbose:
                    # Display detailed info
                    self.stdout.write(f'\n  ✓ {courier.name}')
                    self.stdout.write(f'    Type: {courier.carrier_type} | Mode: {courier.carrier_mode}')
                    self.stdout.write(f'    Logic: {courier.rate_logic} | Active: {courier.is_active}')
                    
                    if courier.rate_logic == 'City_To_City':
                        city_count = len(rate_card.get('routing_logic', {}).get('city_rates', {}))
                        self.stdout.write(f'    Cities configured: {city_count}')
                        
                        # Show first few cities as sample
                        if city_count > 0:
                            cities = list(rate_card['routing_logic']['city_rates'].keys())[:5]
                            self.stdout.write(f'    Sample cities: {", ".join(cities)}...')
                else:
                    # Just show a simple checkmark
                    self.stdout.write(f'  ✓ {courier.name}')
            
            # Write to file with pretty formatting
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open('w', encoding='utf-8') as f:
                json.dump(rate_cards, f, indent=4, ensure_ascii=False)
            
            # Success message
            self.stdout.write('\n' + '='*60)
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Successfully exported {len(rate_cards)} courier(s) to master_card.json'
                )
            )
            self.stdout.write('='*60)
            
            # Summary of city-to-city carriers
            city_carriers = [c for c in couriers if c.rate_logic == 'City_To_City']
            if city_carriers:
                self.stdout.write('\nCity-to-City Carriers:')
                for carrier in city_carriers:
                    city_count = len(carrier.rate_card.get('routing_logic', {}).get('city_rates', {}))
                    self.stdout.write(f'  • {carrier.name}: {city_count} cities')
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'✗ Error exporting data: {str(e)}')
            )
            raise
