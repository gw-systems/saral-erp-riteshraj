# Generated manually on 2026-01-07 to consolidate fix scripts
# Replaces: fix_bluedart.py, fix_pricing_logic.py, update_acpl.py, update_vtrans.py

from django.db import migrations
import json

# DO NOT import from the app (courier.*) here. 
# Migrations must be self-contained to avoid circular dependency and breakage on refactor.

def fix_bluedart_config(apps, schema_editor):
    """
    Configure BlueDart carrier for Region_CSV pricing logic.
    """
    Courier = apps.get_model('courier', 'Courier')
    
    try:
        # Using hardcoded name to match constants.CarrierNames.BLUEDART
        name = "Blue Dart"
        csv_file = "BlueDart_Serviceable Pincodes.csv"
        
        bd = Courier.objects.get(name=name)
        bd.serviceable_pincode_csv = csv_file
        bd.save()
        print(f"Successfully configured BlueDart with {csv_file}")
    except Courier.DoesNotExist:
        print(f"BlueDart Configuration: Carrier 'Blue Dart' not found. Skipping.")


def reverse_bluedart_config(apps, schema_editor):
    """Reverse BlueDart configuration."""
    Courier = apps.get_model('courier', 'Courier')
    try:
        bd = Courier.objects.get(name="Blue Dart")
        bd.serviceable_pincode_csv = None
        bd.save()
    except Courier.DoesNotExist:
        pass


def fix_acpl_config(apps, schema_editor):
    """
    Configure ACPL Surface 50kg for City-to-City logic with Bhiwandi hub.
    """
    Courier = apps.get_model('courier', 'Courier')
    
    try:
        acpl = Courier.objects.filter(name__icontains='ACPL').first()
        if not acpl:
            print("ACPL Configuration: Carrier not found. Skipping.")
            return
        
        # Set hub and CSV configuration
        acpl.hub_city = "bhiwandi"
        acpl.serviceable_pincode_csv = "ACPL_Serviceable_Pincodes.csv"
        acpl.required_source_city = "bhiwandi"
        acpl.min_weight = 50.0
        acpl.fuel_surcharge_percent = 0
        
        # Update rate card with fee structures
        rc = acpl.legacy_rate_card_backup or {}
        
        # Fixed fees
        if 'fixed_fees' not in rc:
            rc['fixed_fees'] = {}
        rc['fixed_fees']['docket_fee'] = 100.0
        rc['fixed_fees']['eway_bill_fee'] = 10.0
        rc['fixed_fees']['cod_fixed'] = 250.0
        
        # Variable fees
        if 'variable_fees' not in rc:
            rc['variable_fees'] = {}
        
        # FOV (Owner's Risk: 0.5% or 50, whichever is higher)
        rc['variable_fees']['owners_risk'] = {
            "percent": 0.005,  # 0.5%
            "min_amount": 50.0
        }
        
        # Hamali (0.5 per kg or 50 min)
        rc['variable_fees']['hamali_per_kg'] = 0.5
        rc['variable_fees']['min_hamali'] = 50.0
        
        # Pickup (Godown Collection): 20 Rs up to 100kg, then 0.1 Rs per kg
        rc['variable_fees']['pickup_slab'] = {
            "slab": 100,
            "base": 20.0,
            "extra_rate": 0.1
        }
        
        # Delivery (Godown Delivery): City-specific
        rc['variable_fees']['delivery_slab'] = {
            "slab": 100,
            "base": 70.0,
            "extra_rate": 0.25,
            "city_exceptions": {
                "mumbai": {
                    "slab": 100,
                    "base": 80.0,
                    "extra_rate": 0.25
                }
            }
        }
        
        # COD configuration
        rc['variable_fees']['cod_percent'] = 0 
        
        # Dynamic fuel surcharge (base diesel price: 90 Rs)
        rc['fuel_config'] = {
            "is_dynamic": True,
            "base_diesel_price": 90.0,
            "diesel_ratio": 0.625
        }
        
        acpl.legacy_rate_card_backup = rc
        acpl.save()
        print(f"Successfully configured ACPL: {acpl.name}")
        
    except Exception as e:
        print(f"Error configuring ACPL: {e}")


def reverse_acpl_config(apps, schema_editor):
    """Reverse ACPL configuration."""
    Courier = apps.get_model('courier', 'Courier')
    try:
        acpl = Courier.objects.filter(name__icontains='ACPL').first()
        if acpl:
            acpl.hub_city = None
            acpl.serviceable_pincode_csv = None
            acpl.required_source_city = None
            acpl.min_weight = 0.5  # Default minimum
            acpl.save()
    except Exception:
        pass


def fix_vtrans_config(apps, schema_editor):
    """
    Configure V-Trans 100kg for Zonal_Custom logic.
    """
    Courier = apps.get_model('courier', 'Courier')
    
    try:
        name = "V-Trans 100kg"
        vtrans = Courier.objects.get(name=name)
        
        # Only switch to Zonal_Custom if zone data exists
        if vtrans.custom_zones.count() > 0:
            vtrans.rate_logic = "Zonal_Custom"
            
            # Update rate card
            rc = vtrans.legacy_rate_card_backup or {}
            
            # Fixed fees
            if 'fixed_fees' not in rc:
                rc['fixed_fees'] = {}
            rc['fixed_fees']['docket_fee'] = 100.0
            
            # Variable fees
            if 'variable_fees' not in rc:
                rc['variable_fees'] = {}
            
            # Hamali
            rc['variable_fees']['hamali_per_kg'] = 0.2
            
            # FOV (Owner's Risk: 0.2%)
            if 'fov_insured_percent' in rc['variable_fees']:
                del rc['variable_fees']['fov_insured_percent']
            
            rc['variable_fees']['owners_risk'] = {
                "percent": 0.002,  # 0.2%
                "min_amount": 0
            }
            
            # Fuel surcharge (10%)
            vtrans.fuel_surcharge_percent = 0.10
            
            vtrans.legacy_rate_card_backup = rc
            vtrans.save()
            print(f"Successfully configured V-Trans: {vtrans.name}")
        else:
            print(f"V-Trans Configuration: No custom zones found. Keeping Zonal_Standard.")
            
    except Courier.DoesNotExist:
        print(f"V-Trans Configuration: Carrier 'V-Trans 100kg' not found. Skipping.")
    except Exception as e:
        print(f"Error configuring V-Trans: {e}")


def reverse_vtrans_config(apps, schema_editor):
    """Reverse V-Trans configuration."""
    Courier = apps.get_model('courier', 'Courier')
    try:
        vtrans = Courier.objects.get(name="V-Trans 100kg")
        vtrans.rate_logic = "Zonal_Standard"
        vtrans.fuel_surcharge_percent = 0
        vtrans.save()
    except Courier.DoesNotExist:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('courier', '0020_courier_hub_city_courier_required_source_city_and_more'),
    ]

    operations = [
        migrations.RunPython(
            fix_bluedart_config,
            reverse_code=reverse_bluedart_config
        ),
        migrations.RunPython(
            fix_acpl_config,
            reverse_code=reverse_acpl_config
        ),
        migrations.RunPython(
            fix_vtrans_config,
            reverse_code=reverse_vtrans_config
        ),
    ]
