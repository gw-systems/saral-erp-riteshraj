"""
Verify imported RapidShyp data from the database.
Usage:
    python manage.py verify_import
"""
from django.core.management.base import BaseCommand
from ...models import Courier, CourierZoneRate


class Command(BaseCommand):
    help = "Verify RapidShyp courier and zone-rate import results."

    def handle(self, *args, **options):
        self.stdout.write("=" * 60)
        self.stdout.write("RapidShyp couriers in DB:")

        rs_couriers = Courier.objects.filter(aggregator='RapidShyp').order_by('name')
        for courier in rs_couriers:
            zone_count = courier.zone_rates.count()
            try:
                other_charges = courier.fees_config.other_charges
            except Exception:
                other_charges = "NO_FEE_STRUCTURE"

            self.stdout.write(
                f"  id={courier.id} | {courier.name} | agg={courier.aggregator} | "
                f"zone_rates={zone_count} | other_charges={other_charges}"
            )

        self.stdout.write(f"\nTotal RapidShyp couriers: {rs_couriers.count()}")

        self.stdout.write("\n" + "=" * 60)
        total_zone_rates = CourierZoneRate.objects.filter(courier__aggregator='RapidShyp').count()
        self.stdout.write(f"Total CourierZoneRate entries for RapidShyp: {total_zone_rates}")

        sample = rs_couriers.first()
        if sample:
            self.stdout.write(f"\nSample zone rates for '{sample.name}':")
            for zone_rate in sample.zone_rates.all()[:10]:
                self.stdout.write(f"  {zone_rate.zone_code} | {zone_rate.rate_type} | {zone_rate.rate}")

        self.stdout.write("\n=== Verification Complete ===")
