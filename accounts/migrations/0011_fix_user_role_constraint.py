# Generated manually to fix CHECK constraint issue
# Django's AlterField doesn't update PostgreSQL CHECK constraints

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_alter_notification_created_at_and_more'),
    ]

    operations = [
        # Drop old constraint
        migrations.RunSQL(
            sql='ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;',
            reverse_sql='-- No reverse operation'
        ),
        # Add new constraint with supply_manager included
        migrations.RunSQL(
            sql="""
                ALTER TABLE users ADD CONSTRAINT users_role_check
                CHECK (role IN (
                    'admin', 'super_user', 'director',
                    'finance_manager', 'operation_controller', 'operation_manager',
                    'sales_manager', 'supply_manager', 'operation_coordinator',
                    'warehouse_manager', 'backoffice', 'crm_executive',
                    'client', 'vendor'
                ));
            """,
            reverse_sql='ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;'
        ),
    ]
