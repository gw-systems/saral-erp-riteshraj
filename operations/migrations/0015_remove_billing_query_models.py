from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0014_add_opened_at_field'),
        ('accounts', '0006_remove_notification_query'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            # Database operations: Drop tables (already done, safe to re-run)
            database_operations=[
                migrations.RunSQL(
                    sql="DROP TABLE IF EXISTS operations_billingquerycomment CASCADE;",
                    reverse_sql=migrations.RunSQL.noop
                ),
                migrations.RunSQL(
                    sql="DROP TABLE IF EXISTS operations_billingqueryactivity CASCADE;",
                    reverse_sql=migrations.RunSQL.noop
                ),
                migrations.RunSQL(
                    sql="DROP TABLE IF EXISTS operations_billingquery CASCADE;",
                    reverse_sql=migrations.RunSQL.noop
                ),
            ],
            # State operations: Tell Django the models are gone
            state_operations=[
                migrations.DeleteModel(name='BillingQueryComment'),
                migrations.DeleteModel(name='BillingQueryActivity'),
                migrations.DeleteModel(name='BillingQuery'),
            ],
        ),
    ]