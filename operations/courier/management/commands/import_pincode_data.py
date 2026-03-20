from pathlib import Path
import pandas as pd
from django.core.management.base import BaseCommand
from ...models import Pincode, ServiceablePincode, Courier


FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"


class Command(BaseCommand):
    help = 'Import pincode data from CSV files into the database'

    def handle(self, *args, **options):
        data_dir = FIXTURES_DIR
        
        # 1. Import Master Pincodes
        self.import_master_pincodes(data_dir)
        
        # 2. Import BlueDart Serviceable Pincodes
        self.import_bluedart_pincodes(data_dir)
        
        self.stdout.write(self.style.SUCCESS('Data import completed successfully.'))

    def import_master_pincodes(self, data_dir):
        msg = "Importing Master Pincodes..."
        self.stdout.write(msg)
        
        path = data_dir / "pincode_master.csv"
        if not path.exists():
            self.stdout.write(self.style.ERROR(f"File not found: {path}"))
            return

        try:
            # Read CSV efficiently
            df = pd.read_csv(path, usecols=["pincode", "office", "district", "state"])
            df.columns = df.columns.str.strip().str.lower()
            
            # Drop duplicates based on pincode (taking the first occurrence as per legacy logic)
            df.drop_duplicates(subset=["pincode"], keep="first", inplace=True)
            
            pincode_objects = []
            for _, row in df.iterrows():
                pincode_objects.append(Pincode(
                    pincode=row['pincode'],
                    office_name=row['office'],
                    district=row['district'],
                    state=row['state'],
                    is_serviceable=True
                ))
            
            # Bulk Create/Update
            # conflict handling: update fields if exists
            Pincode.objects.bulk_create(
                pincode_objects, 
                batch_size=1000, 
                ignore_conflicts=True # Or update_conflicts=True if we want to refresh data
            )
            # Since ignore_conflicts=True, we won't update existing. 
            # Given this is master data, that's acceptable for now.
            
            self.stdout.write(self.style.SUCCESS(f"Imported {len(pincode_objects)} master pincodes."))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error importing master pincodes: {e}"))


    def import_bluedart_pincodes(self, data_dir):
        carrier_name = "Standalone Blue Dart"
        self.stdout.write(f"Importing Serviceable Pincodes for {carrier_name}...")
        
        # Ensure Carrier Exists
        try:
            courier = Courier.objects.get(name=carrier_name)
        except Courier.DoesNotExist:
            self.stdout.write(self.style.WARNING(f"Courier {carrier_name} not found. Skipping."))
            return

        path = data_dir / "BlueDart_Serviceable Pincodes.csv"
        if not path.exists():
            self.stdout.write(self.style.ERROR(f"File not found: {path}"))
            return

        try:
            df = pd.read_csv(path)
            # Normalize columns
            df.columns = df.columns.str.strip()
            
            # Clean data
            obj_cols = df.select_dtypes(['object']).columns
            df[obj_cols] = df[obj_cols].apply(lambda x: x.astype(str).str.strip() if pd.api.types.is_string_dtype(x) else x)
            
            serviceable_objects = []
            
            # Determine pincode column
            pin_col = "PINCODE" if "PINCODE" in df.columns else "Pincode"
            if pin_col not in df.columns:
                self.stdout.write(self.style.ERROR(f"Column {pin_col} not found in CSV"))
                return

            # Clear existing data for this courier
            count_deleted, _ = ServiceablePincode.objects.filter(courier=courier).delete()
            self.stdout.write(f"Deleted {count_deleted} existing records for {carrier_name}.")

            for _, row in df.iterrows():
                try:
                    pincode_val = int(row[pin_col])
                except (ValueError, TypeError):
                    continue # Skip invalid pincodes
                
                is_edl = str(row.get("Extended Delivery Location", "N")).upper() == "Y"
                dist_val = row.get("EDL Distance", 0)
                try:
                    edl_dist = float(dist_val) if pd.notna(dist_val) and dist_val != "" else 0.0
                except ValueError:
                    edl_dist = 0.0
                    
                is_embargo = str(row.get("Embargo", "N")).upper() == "Y"
                
                serviceable_objects.append(ServiceablePincode(
                    courier=courier,
                    pincode=pincode_val,
                    region_code=row.get("REGION"),
                    is_edl=is_edl,
                    edl_distance=edl_dist,
                    is_embargo=is_embargo,
                    # Assumption: If in list, it is serviceable (unless embargo)
                    is_cod_available=not is_embargo,
                    is_prepaid_available=not is_embargo,
                    is_pickup_available=not is_embargo,
                ))

            ServiceablePincode.objects.bulk_create(serviceable_objects, batch_size=1000)
            self.stdout.write(self.style.SUCCESS(f"Imported {len(serviceable_objects)} serviceable pincodes for {carrier_name}."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error importing BlueDart data: {e}"))
