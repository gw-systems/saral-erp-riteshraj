# dropdown_master_data/migrations/0006_prepare_data_for_fk_conversion.py

from django.db import migrations


def prepare_data_for_fk_conversion(apps, schema_editor):
    """
    Comprehensive data preparation before operations.0033 converts varchar fields to FK fields.
    
    This migration:
    1. Adds missing dropdown values that are referenced by existing data
    2. Normalizes data values to match dropdown codes (case, typos, etc.)
    3. Converts empty strings to NULL for nullable FK fields
    """
    from django.db import connection
    
    # =========================================================================
    # PART 1: Add missing dropdown values
    # =========================================================================
    
    # StorageUnit - add 'lumpsum' (used in storagerate.space_type)
    StorageUnit = apps.get_model('dropdown_master_data', 'StorageUnit')
    StorageUnit.objects.get_or_create(
        code='lumpsum',
        defaults={'label': 'Lumpsum', 'is_active': True, 'display_order': 70}
    )
    
    # =========================================================================
    # PART 2: Normalize data to match dropdown codes
    # =========================================================================
    
    with connection.cursor() as cursor:
        # DailySpaceUtilization.unit - normalize case
        # 'Sq. Ft.' -> 'sqft', 'Pallet' -> 'pallet', 'Order' -> 'order'
        cursor.execute("""
            UPDATE operations_dailyspaceutilization 
            SET unit = CASE 
                WHEN unit = 'Sq. Ft.' THEN 'sqft'
                WHEN unit = 'Pallet' THEN 'pallet'
                WHEN unit = 'Order' THEN 'order'
                ELSE unit
            END
            WHERE unit IN ('Sq. Ft.', 'Pallet', 'Order')
        """)
        
        # ValueAddedService.service_type - fix typo
        # 'labelling' -> 'labeling'
        cursor.execute("""
            UPDATE operations_valueaddedservice 
            SET service_type = 'labeling'
            WHERE service_type = 'labelling'
        """)
        
        # =====================================================================
        # PART 3: Handle nullable FK fields - convert empty strings to NULL
        # =====================================================================
        
        # DisputeLog.severity - nullable FK field
        # First drop NOT NULL constraint if it exists, then convert '' to NULL
        cursor.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'operations_disputelog' 
                    AND column_name = 'severity' 
                    AND is_nullable = 'NO'
                ) THEN
                    ALTER TABLE operations_disputelog ALTER COLUMN severity DROP NOT NULL;
                END IF;
            END $$;
        """)
        
        cursor.execute("""
            UPDATE operations_disputelog 
            SET severity = NULL 
            WHERE severity = '' OR severity IS NULL
        """)
        
        # HandlingRate.channel - nullable FK field
        cursor.execute("""
            UPDATE operations_handlingrate 
            SET channel = NULL 
            WHERE channel = ''
        """)
        
        # StorageRate.space_type - nullable FK field
        cursor.execute("""
            UPDATE operations_storagerate 
            SET space_type = NULL 
            WHERE space_type = ''
        """)
        
        # StorageRateSlab.space_type - nullable FK field
        cursor.execute("""
            UPDATE operations_storagerateslab 
            SET space_type = NULL 
            WHERE space_type = ''
        """)


class Migration(migrations.Migration):
    dependencies = [
        ('dropdown_master_data', '0005_fill_missing_from_old_004'),
    ]

    run_before = [
        ('operations', '0033_alter_agreementrenewallog_options_and_more'),
    ]

    operations = [
        migrations.RunPython(prepare_data_for_fk_conversion, migrations.RunPython.noop),
    ]