from django.core.management.base import BaseCommand
from django.db import transaction

from ...models import Courier
from ...models_refactored import FeeStructure, ServiceConstraints, FuelConfiguration, RoutingLogic

class Command(BaseCommand):
    help = 'Migrate data from Courier model to normalized tables'

    def handle(self, *args, **kwargs):
        couriers = Courier.objects.all()
        for courier in couriers:
            self.stdout.write(f"Migrating {courier.name}...")
            
            with transaction.atomic():
                # Check if already migrated? (e.g. if link exists)
                if hasattr(courier, 'fees_config'):
                     self.stdout.write(f"Skipping {courier.name} (already has fees config)")
                     # Actually we should update it if we want to be safe, but creating new will fail uniqueness if OneToOne?
                     # No, we removed standard Courier.fees OneToOne. 
                     # FeeStructure.courier_link is OneToOne.
                
                # 1. Fee Structure
                fees, _ = FeeStructure.objects.update_or_create(
                    courier_link=courier,
                    defaults={
                        'docket_fee': courier.docket_fee,
                        'eway_bill_fee': courier.eway_bill_fee,
                        'appointment_delivery_fee': courier.appointment_delivery_fee,
                        'cod_fixed': courier.cod_charge_fixed,
                        'cod_percent': courier.cod_charge_percent,
                        'hamali_per_kg': courier.hamali_per_kg,
                        'min_hamali': courier.min_hamali,
                        'fov_min': courier.fov_min,
                        'fov_insured_percent': courier.fov_insured_percent,
                        'fov_uninsured_percent': courier.fov_uninsured_percent,
                        'damage_claim_percent': courier.damage_claim_percent
                    }
                )

                # 2. Constraints
                constraints, _ = ServiceConstraints.objects.update_or_create(
                    courier_link=courier,
                    defaults={
                        'min_weight': courier.min_weight,
                        'max_weight': courier.max_weight,
                        'volumetric_divisor': courier.volumetric_divisor,
                        'required_source_city': courier.required_source_city,
                    }
                )

                # 3. Fuel
                fuel, _ = FuelConfiguration.objects.update_or_create(
                    courier_link=courier,
                    defaults={
                        'is_dynamic': courier.fuel_is_dynamic,
                        'base_price': courier.fuel_base_price,
                        'ratio': courier.fuel_ratio,
                        'surcharge_percent': courier.fuel_surcharge_percent
                    }
                )

                # 4. Routing
                routing, _ = RoutingLogic.objects.update_or_create(
                    courier_link=courier,
                    defaults={
                        'logic_type': courier.rate_logic,
                        'serviceable_pincode_csv': courier.serviceable_pincode_csv,
                        'hub_city': courier.hub_city,
                        'hub_pincode_prefixes': courier.hub_pincode_prefixes
                    }
                )
                
            self.stdout.write(self.style.SUCCESS(f"Migrated {courier.name}"))
