from django.db import migrations


def populate_monthly_billing_status(apps, schema_editor):
    """
    Populate MonthlyBillingStatus dropdown with required workflow states.
    These values are referenced by MonthlyBilling.status field (default='draft').
    """
    MonthlyBillingStatus = apps.get_model('dropdown_master_data', 'MonthlyBillingStatus')

    statuses = [
        ('draft', 'Draft', 10),
        ('submitted', 'Submitted', 20),
        ('pending_controller', 'Pending Controller Review', 30),
        ('controller_rejected', 'Controller Rejected', 35),
        ('pending_finance', 'Pending Finance Review', 40),
        ('finance_rejected', 'Finance Rejected', 45),
        ('approved', 'Approved', 50),
    ]

    for code, label, display_order in statuses:
        MonthlyBillingStatus.objects.get_or_create(
            code=code,
            defaults={
                'label': label,
                'is_active': True,
                'display_order': display_order,
            },
        )

    print(f"Populated {len(statuses)} MonthlyBillingStatus values")


class Migration(migrations.Migration):

    dependencies = [
        ('dropdown_master_data', '0006_prepare_data_for_fk_conversion'),
    ]

    operations = [
        migrations.RunPython(
            populate_monthly_billing_status,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
