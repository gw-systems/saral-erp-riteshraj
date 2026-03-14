from django.db import migrations


def populate_approval_action(apps, schema_editor):
    """
    Populate ApprovalAction dropdown with required workflow actions.
    These values are used by MonthlyBilling.controller_action and finance_action fields.
    Both default to 'pending'.
    """
    ApprovalAction = apps.get_model('dropdown_master_data', 'ApprovalAction')
    
    actions = [
        ('pending', 'Pending Review', 10),
        ('approved', 'Approved', 20),
        ('rejected', 'Rejected', 30),
    ]
    
    for code, label, display_order in actions:
        ApprovalAction.objects.get_or_create(
            code=code,
            defaults={
                'label': label,
                'is_active': True,
                'display_order': display_order
            }
        )
    
    print(f"✅ Populated {len(actions)} ApprovalAction values")


class Migration(migrations.Migration):

    dependencies = [
        ('dropdown_master_data', '0007_populate_monthly_billing_status'),
    ]

    operations = [
        migrations.RunPython(
            populate_approval_action,
            reverse_code=migrations.RunPython.noop
        ),
    ]