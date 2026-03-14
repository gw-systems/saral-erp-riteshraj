# Generated manually to migrate existing data to line items
from django.db import migrations


def migrate_existing_billings_to_line_items(apps, schema_editor):
    """
    Migrate existing MonthlyBilling records from single-value fields to line items.

    Old approach: Single fields like storage_min_space, storage_additional_space, etc.
    New approach: Multiple line item records in separate tables

    Note: MonthlyBilling is an unmanaged model (managed=False), so AddField migrations
    don't actually create columns. This migration checks column existence before querying
    to handle fresh databases (CI) where the table may not have all expected columns.
    """
    from django.db import connection
    from decimal import Decimal

    MonthlyBilling = apps.get_model('operations', 'MonthlyBilling')
    MonthlyBillingStorageItem = apps.get_model('operations', 'MonthlyBillingStorageItem')
    MonthlyBillingHandlingItem = apps.get_model('operations', 'MonthlyBillingHandlingItem')
    MonthlyBillingTransportItem = apps.get_model('operations', 'MonthlyBillingTransportItem')
    MonthlyBillingVASItem = apps.get_model('operations', 'MonthlyBillingVASItem')

    # Check if the unmanaged table exists and has the expected columns
    with connection.cursor() as cursor:
        # Use information_schema to safely check table existence without touching
        # the table itself — avoids aborting the PostgreSQL transaction on fresh DBs.
        cursor.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'monthly_billings'"
        )
        if cursor.fetchone() is None:
            # Table doesn't exist (fresh CI database) — nothing to migrate
            return

        cursor.execute("SELECT COUNT(*) FROM monthly_billings")
        row_count = cursor.fetchone()[0]
        if row_count == 0:
            # No data to migrate
            return

        # Check if transport quantity columns exist (added manually, not by Django migrations)
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'monthly_billings' AND column_name = 'vendor_transport_quantity'
        """)
        has_transport_qty = cursor.fetchone() is not None

        if not has_transport_qty:
            # Columns don't exist (fresh database or CI) — skip data migration
            return

    # Use raw SQL to get actual database values
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, storage_min_space, storage_additional_space, storage_unit_type, storage_days,
                   client_storage_rate, client_storage_billing, vendor_storage_rate, vendor_storage_cost, storage_remarks,
                   handling_in_quantity, handling_in_unit_type, handling_in_channel, handling_in_base_type,
                   client_handling_in_rate, client_handling_in_billing, vendor_handling_in_rate, vendor_handling_in_cost, handling_in_remarks,
                   handling_out_quantity, handling_out_unit_type, handling_out_channel, handling_out_base_type,
                   client_handling_out_rate, client_handling_out_billing, vendor_handling_out_rate, vendor_handling_out_cost, handling_out_remarks,
                   vendor_transport_vehicle_type, vendor_transport_quantity, vendor_transport_amount, vendor_transport_remarks,
                   client_transport_vehicle_type, client_transport_quantity, client_transport_amount, client_transport_remarks,
                   vas_service_type, vendor_vas_service_type, vas_quantity, vas_unit,
                   client_vas_rate, client_vas_billing, vendor_vas_rate, vendor_vas_cost, vas_remarks
            FROM monthly_billings
        """)

        columns = [col[0] for col in cursor.description]
        billings_data = [dict(zip(columns, row)) for row in cursor.fetchall()]

    # Process each billing
    for data in billings_data:
        billing = MonthlyBilling.objects.get(id=data['id'])

        # STORAGE: Create one line item if there's storage data
        if (data['storage_min_space'] and data['storage_min_space'] > 0) or \
           (data['storage_additional_space'] and data['storage_additional_space'] > 0) or \
           (data['client_storage_billing'] and data['client_storage_billing'] > 0) or \
           (data['vendor_storage_cost'] and data['vendor_storage_cost'] > 0):

            MonthlyBillingStorageItem.objects.create(
                monthly_billing=billing,
                row_order=0,
                # Client side
                client_min_space=data['storage_min_space'] or 0,
                client_additional_space=data['storage_additional_space'] or 0,
                client_storage_unit_type_id=data['storage_unit_type'],
                client_storage_days=data['storage_days'] or 0,
                client_rate=data['client_storage_rate'],
                client_billing=data['client_storage_billing'] or 0,
                # Vendor side (same quantities/unit as client in old approach)
                vendor_min_space=data['storage_min_space'] or 0,
                vendor_additional_space=data['storage_additional_space'] or 0,
                vendor_storage_unit_type_id=data['storage_unit_type'],
                vendor_storage_days=data['storage_days'] or 0,
                vendor_rate=data['vendor_storage_rate'],
                vendor_cost=data['vendor_storage_cost'] or 0,
                remarks=data['storage_remarks'] or ''
            )

        # HANDLING IN: Create one line item if there's handling in data
        if (data['handling_in_quantity'] and data['handling_in_quantity'] > 0) or \
           (data['client_handling_in_billing'] and data['client_handling_in_billing'] > 0) or \
           (data['vendor_handling_in_cost'] and data['vendor_handling_in_cost'] > 0):

            MonthlyBillingHandlingItem.objects.create(
                monthly_billing=billing,
                direction='in',
                row_order=0,
                # Client side
                client_quantity=data['handling_in_quantity'] or 0,
                client_unit_type_id=data['handling_in_unit_type'],
                client_channel_id=data['handling_in_channel'],
                client_base_type_id=data['handling_in_base_type'],
                client_rate=data['client_handling_in_rate'],
                client_billing=data['client_handling_in_billing'] or 0,
                # Vendor side (same quantity/unit as client in old approach)
                vendor_quantity=data['handling_in_quantity'] or 0,
                vendor_unit_type_id=data['handling_in_unit_type'],
                vendor_channel_id=data['handling_in_channel'],
                vendor_base_type_id=data['handling_in_base_type'],
                vendor_rate=data['vendor_handling_in_rate'],
                vendor_cost=data['vendor_handling_in_cost'] or 0,
                remarks=data['handling_in_remarks'] or ''
            )

        # HANDLING OUT: Create one line item if there's handling out data
        if (data['handling_out_quantity'] and data['handling_out_quantity'] > 0) or \
           (data['client_handling_out_billing'] and data['client_handling_out_billing'] > 0) or \
           (data['vendor_handling_out_cost'] and data['vendor_handling_out_cost'] > 0):

            MonthlyBillingHandlingItem.objects.create(
                monthly_billing=billing,
                direction='out',
                row_order=0,
                # Client side
                client_quantity=data['handling_out_quantity'] or 0,
                client_unit_type_id=data['handling_out_unit_type'],
                client_channel_id=data['handling_out_channel'],
                client_base_type_id=data['handling_out_base_type'],
                client_rate=data['client_handling_out_rate'],
                client_billing=data['client_handling_out_billing'] or 0,
                # Vendor side
                vendor_quantity=data['handling_out_quantity'] or 0,
                vendor_unit_type_id=data['handling_out_unit_type'],
                vendor_channel_id=data['handling_out_channel'],
                vendor_base_type_id=data['handling_out_base_type'],
                vendor_rate=data['vendor_handling_out_rate'],
                vendor_cost=data['vendor_handling_out_cost'] or 0,
                remarks=data['handling_out_remarks'] or ''
            )

        # TRANSPORT VENDOR: Create one line item if there's vendor transport data
        if (data['vendor_transport_quantity'] and data['vendor_transport_quantity'] > 0) or \
           (data['vendor_transport_amount'] and data['vendor_transport_amount'] > 0):

            MonthlyBillingTransportItem.objects.create(
                monthly_billing=billing,
                side='vendor',
                row_order=0,
                vehicle_type_id=data['vendor_transport_vehicle_type'],
                quantity=data['vendor_transport_quantity'] or 0,
                amount=data['vendor_transport_amount'] or 0,
                remarks=data['vendor_transport_remarks'] or ''
            )

        # TRANSPORT CLIENT: Create one line item if there's client transport data
        if (data['client_transport_quantity'] and data['client_transport_quantity'] > 0) or \
           (data['client_transport_amount'] and data['client_transport_amount'] > 0):

            MonthlyBillingTransportItem.objects.create(
                monthly_billing=billing,
                side='client',
                row_order=0,
                vehicle_type_id=data['client_transport_vehicle_type'],
                quantity=data['client_transport_quantity'] or 0,
                amount=data['client_transport_amount'] or 0,
                remarks=data['client_transport_remarks'] or ''
            )

        # VAS: Create one line item if there's VAS data
        if (data['vas_quantity'] and data['vas_quantity'] > 0) or \
           (data['client_vas_billing'] and data['client_vas_billing'] > 0) or \
           (data['vendor_vas_cost'] and data['vendor_vas_cost'] > 0):

            MonthlyBillingVASItem.objects.create(
                monthly_billing=billing,
                row_order=0,
                # Client side
                client_service_type_id=data['vas_service_type'],
                client_quantity=data['vas_quantity'] or 0,
                client_unit_id=data['vas_unit'],
                client_rate=data['client_vas_rate'],
                client_billing=data['client_vas_billing'] or 0,
                # Vendor side (fallback to client service type if not set)
                vendor_service_type_id=data['vendor_vas_service_type'] or data['vas_service_type'],
                vendor_quantity=data['vas_quantity'] or 0,
                vendor_unit_id=data['vas_unit'],
                vendor_rate=data['vendor_vas_rate'],
                vendor_cost=data['vendor_vas_cost'] or 0,
                remarks=data['vas_remarks'] or ''
            )


def reverse_migration(apps, schema_editor):
    """
    Reverse migration: Delete all line items (data will be preserved in parent fields).
    """
    MonthlyBillingStorageItem = apps.get_model('operations', 'MonthlyBillingStorageItem')
    MonthlyBillingHandlingItem = apps.get_model('operations', 'MonthlyBillingHandlingItem')
    MonthlyBillingTransportItem = apps.get_model('operations', 'MonthlyBillingTransportItem')
    MonthlyBillingVASItem = apps.get_model('operations', 'MonthlyBillingVASItem')

    MonthlyBillingStorageItem.objects.all().delete()
    MonthlyBillingHandlingItem.objects.all().delete()
    MonthlyBillingTransportItem.objects.all().delete()
    MonthlyBillingVASItem.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0052_monthlybillinghandlingitem_monthlybillingstorageitem_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_existing_billings_to_line_items, reverse_migration),
    ]
