from django.db import migrations


def repair_monthly_billing_schema(apps, schema_editor):
    table_name = 'monthly_billings'
    wanted_columns = {
        'vendor_transport_quantity': "numeric(12,4) NOT NULL DEFAULT 0",
        'client_transport_quantity': "numeric(12,4) NOT NULL DEFAULT 0",
        'vendor_vas_service_type': "varchar(50) NULL",
        'client_infrastructure_amount': "numeric(15,4) NOT NULL DEFAULT 0",
        'vendor_infrastructure_cost': "numeric(15,4) NOT NULL DEFAULT 0",
        'infrastructure_remarks': "text NOT NULL DEFAULT ''",
        'storage_override_reason': "text NOT NULL DEFAULT ''",
        'storage_client_variance': "numeric(15,2) NULL",
        'storage_vendor_variance': "numeric(15,2) NULL",
        'handling_in_override_reason': "text NOT NULL DEFAULT ''",
        'handling_in_client_variance': "numeric(15,2) NULL",
        'handling_in_vendor_variance': "numeric(15,2) NULL",
        'handling_out_override_reason': "text NOT NULL DEFAULT ''",
        'handling_out_client_variance': "numeric(15,2) NULL",
        'handling_out_vendor_variance': "numeric(15,2) NULL",
        'mis_document': "varchar(100) NULL",
        'transport_document': "varchar(100) NULL",
        'other_document': "varchar(100) NULL",
        'included_adhoc_ids': "jsonb NOT NULL DEFAULT '[]'::jsonb",
    }

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
            """,
            [table_name],
        )
        existing_columns = {row[0] for row in cursor.fetchall()}

        for column_name, definition in wanted_columns.items():
            if column_name not in existing_columns:
                cursor.execute(
                    f'ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}'
                )


def reverse_noop(apps, schema_editor):
    # Keep the repair migration non-destructive.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0065_ensure_transport_quantity_columns'),
    ]

    operations = [
        migrations.RunPython(repair_monthly_billing_schema, reverse_noop),
    ]
