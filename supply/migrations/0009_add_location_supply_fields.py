# Ensure supply-specific fields exist on the locations table.
#
# On a fresh DB, projects migrations create the locations table WITHOUT
# state_code and city_code:
#   - state_code: projects/0016 removes it from the projects.Location model
#   - city_code:  was never part of projects.Location
#
# supply/0001_initial uses ConditionalCreateModel which skips table creation
# when the table already exists, so those columns are never added on fresh DBs.
#
# This migration uses RunPython (not AddField) so Django's model state — which
# already includes these fields from 0001_initial — is not touched.

from django.db import migrations


def add_location_supply_fields(apps, schema_editor):
    """Add state_code and city_code to locations table if columns are missing."""
    with schema_editor.connection.cursor() as cursor:
        # Check and add state_code
        cursor.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'locations' AND column_name = 'state_code'"
        )
        if not cursor.fetchone():
            cursor.execute(
                "ALTER TABLE locations ADD COLUMN state_code VARCHAR(2) NULL"
            )

        # Check and add city_code
        cursor.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'locations' AND column_name = 'city_code'"
        )
        if not cursor.fetchone():
            cursor.execute(
                "ALTER TABLE locations ADD COLUMN city_code VARCHAR(3) NULL"
            )

        # Add indexes if missing
        cursor.execute(
            "SELECT 1 FROM pg_indexes "
            "WHERE tablename = 'locations' AND indexname = 'locations_state_c_7f0345_idx'"
        )
        if not cursor.fetchone():
            cursor.execute(
                "CREATE INDEX locations_state_c_7f0345_idx ON locations (state_code)"
            )

        cursor.execute(
            "SELECT 1 FROM pg_indexes "
            "WHERE tablename = 'locations' AND indexname = 'locations_city_co_144673_idx'"
        )
        if not cursor.fetchone():
            cursor.execute(
                "CREATE INDEX locations_city_co_144673_idx ON locations (city_code)"
            )


class Migration(migrations.Migration):

    dependencies = [
        ('supply', '0008_add_missing_cities'),
    ]

    operations = [
        migrations.RunPython(
            add_location_supply_fields,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
