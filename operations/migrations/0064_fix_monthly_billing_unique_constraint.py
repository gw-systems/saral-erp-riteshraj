from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0063_porterinvoicesession_porterinvoicefile_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                -- Add service_month column if it doesn't exist (no-op on managed=False models)
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'monthly_billings'
                          AND column_name = 'service_month'
                    ) THEN
                        ALTER TABLE monthly_billings
                            ADD COLUMN service_month date NULL;
                    END IF;
                END $$;

                -- Drop old billing_month unique constraints
                ALTER TABLE monthly_billings
                    DROP CONSTRAINT IF EXISTS monthly_billings_project_id_billing_month_key;
                ALTER TABLE monthly_billings
                    DROP CONSTRAINT IF EXISTS monthly_billings_project_id_billing_month_089b3f63_uniq;

                -- Add new service_month unique constraint
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'monthly_billings_project_id_service_month_key'
                    ) THEN
                        ALTER TABLE monthly_billings
                            ADD CONSTRAINT monthly_billings_project_id_service_month_key
                            UNIQUE (project_id, service_month);
                    END IF;
                END $$;
            """,
            reverse_sql="""
                ALTER TABLE monthly_billings
                    DROP CONSTRAINT IF EXISTS monthly_billings_project_id_service_month_key;

                ALTER TABLE monthly_billings
                    ADD CONSTRAINT monthly_billings_project_id_billing_month_key
                    UNIQUE (project_id, billing_month);
            """,
        ),
    ]
