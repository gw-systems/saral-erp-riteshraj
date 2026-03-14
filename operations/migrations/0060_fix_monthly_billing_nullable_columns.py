from django.db import migrations


def fix_nullable_columns(apps, schema_editor):
    """
    Fix: monthly_billings table columns are NOT NULL but must allow NULL.

    Same root cause as 0054 — MonthlyBilling has managed=False, so Django's
    AddField migrations are no-ops. Some columns may not physically exist on
    fresh databases. We query information_schema to only ALTER columns that
    actually exist, making this idempotent across all environments.
    """
    from django.db import connection

    with connection.cursor() as cursor:
        # Check if the unmanaged table exists
        cursor.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'monthly_billings'
        """)
        if cursor.fetchone() is None:
            return

        # Get all existing columns on the table
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'monthly_billings'
        """)
        existing_columns = {row[0] for row in cursor.fetchall()}

        # Columns we want to make nullable
        target_columns = [
            'storage_min_space', 'storage_additional_space', 'storage_unit_type', 'storage_days',
            'vendor_storage_rate', 'vendor_storage_cost', 'client_storage_rate', 'client_storage_billing',
            'handling_in_quantity', 'handling_in_unit_type', 'handling_in_channel', 'handling_in_base_type',
            'vendor_handling_in_rate', 'vendor_handling_in_cost', 'client_handling_in_rate', 'client_handling_in_billing',
            'handling_out_quantity', 'handling_out_unit_type', 'handling_out_channel', 'handling_out_base_type',
            'vendor_handling_out_rate', 'vendor_handling_out_cost', 'client_handling_out_rate', 'client_handling_out_billing',
            'client_transport_vehicle_type', 'client_transport_quantity', 'client_transport_amount',
            'vendor_transport_vehicle_type', 'vendor_transport_quantity', 'vendor_transport_amount',
            'vas_service_type', 'vendor_vas_service_type', 'vas_quantity', 'vas_unit',
            'client_vas_rate', 'client_vas_billing', 'vendor_vas_rate', 'vendor_vas_cost',
            'client_infrastructure_amount', 'vendor_infrastructure_cost',
        ]

        # Only alter columns that actually exist in the database
        columns_to_alter = [col for col in target_columns if col in existing_columns]

        if not columns_to_alter:
            return

        alter_clauses = ', '.join(
            f'ALTER COLUMN {col} DROP NOT NULL' for col in columns_to_alter
        )
        cursor.execute(f'ALTER TABLE monthly_billings {alter_clauses};')


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0059_fix_vas_hours_decimal_precision'),
    ]

    operations = [
        migrations.RunPython(fix_nullable_columns, migrations.RunPython.noop),
    ]
