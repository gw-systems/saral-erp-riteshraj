
import json
from pathlib import Path
from django.core.management.base import BaseCommand
from ...models import Courier


FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"


class Command(BaseCommand):
    help = 'Load ALL courier configurations from master_card.json into the database'

    def handle(self, *args, **options):
        # 1. Load JSON file
        json_path = FIXTURES_DIR / "master_card.json"
        
        if not json_path.exists():
            self.stdout.write(self.style.ERROR(f'Config file not found: {json_path}'))
            return

        with json_path.open("r", encoding='utf-8') as f:
            data = json.load(f)

        if not isinstance(data, list):
             self.stdout.write(self.style.ERROR(f'master_card.json must be a list of carrier objects'))
             return

        self.stdout.write(f"Found {len(data)} carriers in master_card.json")

        for carrier_data in data:
            try:
                # 2. Update or Create Courier Object
                carrier_name = carrier_data.get("carrier_name")
                if not carrier_name:
                    self.stdout.write(self.style.WARNING('Skipping entry with no carrier_name'))
                    continue

                courier, created = Courier.objects.get_or_create(name=carrier_name)
                
                # 3. Update fields
                courier.is_active = carrier_data.get("active", True)
                courier.carrier_type = carrier_data.get("type", "Courier")
                courier.carrier_mode = carrier_data.get("mode", "Surface")
                
                # Determine logic type mapping
                json_logic = carrier_data.get("routing_logic", {}).get("type") # e.g. pincode_region_csv
                logic_field = carrier_data.get("logic") # e.g. Zonal, city_to_city

                if json_logic == "pincode_region_csv":
                    courier.rate_logic = "Region_CSV"
                elif logic_field == "city_to_city":
                     courier.rate_logic = "City_To_City"
                elif logic_field == "Zonal_Custom":
                     courier.rate_logic = "Zonal_Custom"
                else:
                     courier.rate_logic = "Zonal_Standard"

                # Config fields
                fuel = carrier_data.get("fuel_config", {})
                courier.fuel_surcharge_percent = fuel.get("flat_percent", 0.0)
                
                fixed_fees = carrier_data.get("fixed_fees", {})
                var_fees = carrier_data.get("variable_fees", {})
                
                courier.cod_charge_fixed = fixed_fees.get("cod_fixed", 0.0)
                courier.cod_charge_percent = var_fees.get("cod_percent", 0.0)
                
                # Min/Max/Divisor
                courier.min_weight = carrier_data.get("min_weight", 0.5)
                courier.max_weight = carrier_data.get("max_weight", 99999.0)
                courier.volumetric_divisor = carrier_data.get("volumetric_divisor", 5000)

                # 4. Set the Rate Card JSON directly
                # This ensures all nested data (like EDL matrix, city rates, etc.) is preserved
                courier.rate_card = carrier_data
                
                # Save
                courier.save()
                
                action = "Created" if created else "Updated"
                self.stdout.write(f"  - {action}: {carrier_name}")
            
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error processing {carrier_data.get('carrier_name')}: {e}"))

        self.stdout.write(self.style.SUCCESS(f'Successfully loaded all couriers.'))
