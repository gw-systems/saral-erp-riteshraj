from django.db import migrations


def ensure_transport_quantity_columns(apps, schema_editor):
    table_name = 'monthly_billings'
    vendor_column = 'vendor_transport_quantity'
    client_column = 'client_transport_quantity'

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
              AND column_name IN (%s, %s)
            """,
            [table_name, vendor_column, client_column],
        )
        existing = {row[0] for row in cursor.fetchall()}

        if vendor_column not in existing:
            cursor.execute(
                f'ALTER TABLE {table_name} '
                f'ADD COLUMN {vendor_column} numeric(12,4) NOT NULL DEFAULT 0'
            )

        if client_column not in existing:
            cursor.execute(
                f'ALTER TABLE {table_name} '
                f'ADD COLUMN {client_column} numeric(12,4) NOT NULL DEFAULT 0'
            )


def reverse_noop(apps, schema_editor):
    # Keep this repair migration non-destructive.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0064_fix_monthly_billing_unique_constraint'),
    ]

    operations = [
        migrations.RunPython(ensure_transport_quantity_columns, reverse_noop),
    ]
