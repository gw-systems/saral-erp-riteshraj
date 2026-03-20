import os
import pandas as pd
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from ...models import Courier, CourierZoneRate, FeeStructure

class Command(BaseCommand):
    help = 'Import Courier Rates from Ultra (2).xlsx'

    def add_arguments(self, parser):
        parser.add_argument('excel_path', type=str, help='Path to the Excel file to import')

    def _clean_decimal(self, val):
        if pd.isna(val) or str(val).strip() == '':
            return Decimal('0.00')
        return Decimal(str(val))

    def handle(self, *args, **kwargs):
        excel_path = kwargs['excel_path']
        if not os.path.exists(excel_path):
            self.stdout.write(self.style.ERROR(f"File not found: {excel_path}"))
            return

        self.stdout.write(self.style.SUCCESS(f"Reading Excel file: {excel_path}"))

        try:
            # Read with header on the second row (index 1)
            df = pd.read_excel(excel_path, header=1)
            
            with transaction.atomic():
                self.process_ultra_rates(df)

            self.stdout.write(self.style.SUCCESS("Successfully imported Ultra rates!"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Import failed: {str(e)}"))
            import traceback
            traceback.print_exc()

    def process_ultra_rates(self, df):
        # The sheet has multiple tables side by side.
        # e.g., Base features, then unnamed: 12, then .1 features, etc.
        # We can detect all 'Courier' columns and process each block of columns
        
        courier_cols = [c for c in df.columns if str(c).startswith('Courier')]
        
        for col_name in courier_cols:
            suffix = col_name[len('Courier'):] # e.g., '', '.1', '.2'
            
            # Map column names with the current suffix
            c_courier = f'Courier{suffix}'
            c_mode = f'Mode{suffix}'
            c_min_wt = f'Min. Weight{suffix}'
            c_type_name = f'Type Name{suffix}'
            c_za = f'z_a{suffix}'
            c_zb = f'z_b{suffix}'
            c_zc = f'z_c{suffix}'
            c_zd = f'z_d{suffix}'
            c_ze = f'z_e{suffix}'
            c_cod = f'cod_charges{suffix}'
            c_cod_pct = f'cod_percentage{suffix}'
            c_other = f'other charges{suffix}'
            
            for index, row in df.iterrows():
                try:
                    courier_name = row.get(c_courier)
                    if pd.isna(courier_name) or str(courier_name).strip() == '' or str(courier_name).strip().lower() == 'nan':
                        continue
                        
                    courier_name = str(courier_name).strip()
                    mode = str(row.get(c_mode, 'Surface')).strip()
                    min_weight = float(row.get(c_min_wt, 0.5)) if not pd.isna(row.get(c_min_wt)) else 0.5
                    type_name = str(row.get(c_type_name, '')).strip().lower()
                    
                    # Create or Get Courier
                    # Aggregator is standalone by default
                    defaults = {
                        'carrier_mode': mode,
                        'min_weight': min_weight,
                    }
                    
                    try:
                        courier = Courier.objects.get(name=courier_name)
                        for k, v in defaults.items():
                            setattr(courier, k, v)
                        courier.save()
                    except Courier.DoesNotExist:
                        # Find surface/air category
                        svc_category = Courier.ServiceCategory.SURFACE if mode.lower() == 'surface' else Courier.ServiceCategory.AIR
                        courier = Courier.objects.create(
                            name=courier_name,
                            carrier_mode=mode,
                            service_category=svc_category,
                            min_weight=min_weight,
                            aggregator=Courier.Aggregator.STANDALONE
                        )
                        
                    # Process FeeStructure
                    cod_fixed = self._clean_decimal(row.get(c_cod))
                    cod_percent = self._clean_decimal(row.get(c_cod_pct))
                    other_charges = self._clean_decimal(row.get(c_other))
                    
                    fees, _ = FeeStructure.objects.get_or_create(courier_link=courier)
                    # We only update fees once or take the max/last value.
                    # Usually, fees are the same across all rows for the same courier.
                    if cod_fixed > Decimal('0.00'): fees.cod_fixed = cod_fixed
                    if cod_percent > Decimal('0.0000'): fees.cod_percent = cod_percent
                    if other_charges > Decimal('0.00'): fees.other_charges = other_charges
                    fees.save()
                    
                    # Process Zone Rates
                    rate_type_mapping = {
                        'forward': CourierZoneRate.RateType.FORWARD,
                        'fwd additional': CourierZoneRate.RateType.ADDITIONAL,
                        'fwd additonal': CourierZoneRate.RateType.ADDITIONAL, # Typo handling
                        'rto': CourierZoneRate.RateType.RTO,
                        'rto additional': CourierZoneRate.RateType.RTO_ADDITIONAL,
                        'return': CourierZoneRate.RateType.REVERSE,
                        'reverse': CourierZoneRate.RateType.REVERSE,
                        'reverse additional': CourierZoneRate.RateType.REVERSE_ADDITIONAL,
                    }
                    
                    if type_name in rate_type_mapping:
                        rate_type = rate_type_mapping[type_name]
                        
                        zones = {
                            'z_a': row.get(c_za),
                            'z_b': row.get(c_zb),
                            'z_c': row.get(c_zc),
                            'z_d': row.get(c_zd),
                            'z_e': row.get(c_ze)
                        }
                        
                        for z_code, z_val in zones.items():
                            if not pd.isna(z_val):
                                CourierZoneRate.objects.update_or_create(
                                    courier=courier,
                                    zone_code=z_code,
                                    rate_type=rate_type,
                                    defaults={'rate': self._clean_decimal(z_val)}
                                )
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"Row {index} skipped due to error: {str(e)}"))
