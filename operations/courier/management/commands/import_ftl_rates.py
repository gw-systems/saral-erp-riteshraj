import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction
import math

from ...models import FTLRate
from ...views.base import invalidate_rates_cache


class Command(BaseCommand):
    help = "Import FTL rates from an Excel file seamlessly merging with existing rates."

    def add_arguments(self, parser):
        parser.add_argument('excel_file', type=str, help='Path to the FTL Excel file')

    def handle(self, *args, **kwargs):
        excel_path = kwargs['excel_file']

        self.stdout.write(self.style.NOTICE(f"Loading FTL Rate Card: {excel_path}"))

        try:
            # Read the Excel file
            df = pd.read_excel(excel_path)
            
            # Expected columns
            expected_cols = ['Source City', 'Destination City', 'Truck Type', 'Rate']
            missing_cols = [c for c in expected_cols if c not in df.columns]
            if missing_cols:
                self.stdout.write(self.style.ERROR(f"Missing required columns in sheet: {missing_cols}"))
                return

            records_processed = 0
            records_updated = 0
            records_created = 0

            # Wrapping in an atomic transaction to ensure data integrity
            with transaction.atomic():
                for index, row in df.iterrows():
                    source = str(row.get('Source City', '')).strip()
                    dest = str(row.get('Destination City', '')).strip()
                    truck_type = str(row.get('Truck Type', '')).strip()
                    rate = row.get('Rate', 0)

                    # Basic validation
                    if not source or not dest or not truck_type or pd.isna(rate):
                        self.stdout.write(self.style.WARNING(f"Skipping row {index + 2}: Missing vital data."))
                        continue
                    
                    if str(source).lower() == 'nan' or str(dest).lower() == 'nan' or str(truck_type).lower() == 'nan':
                        continue

                    try:
                        rate_val = float(rate)
                    except ValueError:
                        self.stdout.write(self.style.WARNING(f"Skipping row {index + 2}: Invalid rate value -> {rate}"))
                        continue

                    # Merge logic (Update or Create)
                    obj, created = FTLRate.objects.update_or_create(
                        source_city=source,
                        destination_city=dest,
                        truck_type=truck_type,
                        defaults={
                            'rate': rate_val
                        }
                    )
                    
                    records_processed += 1
                    if created:
                        records_created += 1
                    else:
                        records_updated += 1
            
            # Invalidate cache so API picks it up
            invalidate_rates_cache()

            self.stdout.write(self.style.SUCCESS(
                f"Successfully parsed FTL rates! "
                f"Processed: {records_processed}, Created: {records_created}, Updated: {records_updated}"
            ))

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"File not found: {excel_path}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"An error occurred during FTL import: {str(e)}"))
