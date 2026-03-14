# Generated manually on 2026-01-19
# Complete and comprehensive data migration to populate ALL required dropdown values

from django.db import migrations


def populate_all_required_dropdown_values(apps, schema_editor):
    """
    Populate ALL dropdown tables with values that are referenced in the database.
    This is a complete migration based on full staging database audit.
    Includes every dropdown value actually used in operations, projects, and tickets data.
    """
    
    # Get all required dropdown models
    AdhocChargeType = apps.get_model('dropdown_master_data', 'AdhocChargeType')
    TransactionSide = apps.get_model('dropdown_master_data', 'TransactionSide')
    DisputeCategory = apps.get_model('dropdown_master_data', 'DisputeCategory')
    DisputeStatus = apps.get_model('dropdown_master_data', 'DisputeStatus')
    Priority = apps.get_model('dropdown_master_data', 'Priority')
    Severity = apps.get_model('dropdown_master_data', 'Severity')
    RenewalActionType = apps.get_model('dropdown_master_data', 'RenewalActionType')
    EscalationActionType = apps.get_model('dropdown_master_data', 'EscalationActionType')
    AlertType = apps.get_model('dropdown_master_data', 'AlertType')
    ProjectStatus = apps.get_model('dropdown_master_data', 'ProjectStatus')
    MISStatus = apps.get_model('dropdown_master_data', 'MISStatus')
    OperationMode = apps.get_model('dropdown_master_data', 'OperationMode')
    HandlingBaseType = apps.get_model('dropdown_master_data', 'HandlingBaseType')
    HandlingDirection = apps.get_model('dropdown_master_data', 'HandlingDirection')
    SalesChannel = apps.get_model('dropdown_master_data', 'SalesChannel')
    StorageUnit = apps.get_model('dropdown_master_data', 'StorageUnit')
    BillingUnit = apps.get_model('dropdown_master_data', 'BillingUnit')
    
    # Define ALL required dropdown values
    # Format: (Model, [(code, label, display_order), ...])
    dropdown_data = [
        (AdhocChargeType, [
            ('equipment', 'Equipment', 10),
            ('extra_handling', 'Extra Handling', 20),
            ('extra_manpower', 'Extra Manpower', 25),
            ('extra_storage', 'Extra Storage', 30),
            ('overtime', 'Overtime', 40),
            ('transport', 'Transport', 50),
            ('vas', 'Value Added Services', 60),
        ]),
        (TransactionSide, [
            ('client', 'Client', 10),
            ('vendor', 'Vendor', 20),
        ]),
        (DisputeCategory, [
            ('operations', 'Operations', 10),
            ('billing', 'Billing', 20),
            ('technical', 'Technical', 30),
        ]),
        (DisputeStatus, [
            ('open', 'Open', 10),
            ('in_progress', 'In Progress', 20),
            ('resolved', 'Resolved', 30),
            ('closed', 'Closed', 40),
        ]),
        (Priority, [
            ('critical', 'Critical', 10),
            ('high', 'High', 20),
            ('medium', 'Medium', 30),
            ('low', 'Low', 40),
        ]),
        (Severity, [
            ('critical', 'Critical', 10),
            ('high', 'High', 20),
            ('medium', 'Medium', 30),
            ('low', 'Low', 40),
        ]),
        (RenewalActionType, [
            ('tracker_created', 'Tracker Created', 10),
            ('email_sent', 'Email Sent', 20),
            ('follow_up', 'Follow Up', 30),
            ('renewed', 'Renewed', 40),
            ('not_renewed', 'Not Renewed', 50),
        ]),
        (EscalationActionType, [
            ('email_sent', 'Email Sent', 10),
            ('call_made', 'Call Made', 20),
            ('meeting_scheduled', 'Meeting Scheduled', 30),
            ('resolved', 'Resolved', 40),
        ]),
        (AlertType, [
            ('info', 'Information', 10),
            ('warning', 'Warning', 20),
            ('error', 'Error', 30),
            ('critical', 'Critical', 40),
        ]),
        (ProjectStatus, [
            ('operation_not_started', 'Operation Not Started', 10),
            ('active', 'Active', 20),
            ('notice_period', 'Notice Period', 30),
            ('inactive', 'Inactive', 40),
        ]),
        (MISStatus, [
            ('mis_daily', 'MIS Daily', 10),
            ('mis_weekly', 'MIS Weekly', 20),
            ('mis_monthly', 'MIS Monthly', 30),
            ('inciflo', 'Inciflo', 40),
            ('mis_automode', 'MIS Automode', 50),
            ('mis_not_required', 'MIS Not Required', 60),
        ]),
        (OperationMode, [
            ('auto_mode', 'Auto Mode', 10),
            ('data_sharing', 'Data Sharing', 20),
            ('active_engagement', 'Active Engagement', 30),
        ]),
        (HandlingBaseType, [
            ('per_box', 'Per Box', 10),
            ('per_kg', 'Per KG', 20),
            ('per_pallet', 'Per Pallet', 30),
            ('per_tonne', 'Per Tonne', 40),
            ('per_unit', 'Per Unit', 50),
        ]),
        (HandlingDirection, [
            ('inbound', 'Inbound', 10),
            ('outbound', 'Outbound', 20),
            ('both', 'Both', 30),
        ]),
        (SalesChannel, [
            ('b2b', 'B2B', 10),
            ('b2c', 'B2C', 20),
            ('rto', 'RTO', 30),
            ('marketplace', 'Marketplace', 40),
        ]),
        (StorageUnit, [
            ('sqft', 'Square Feet', 10),
            ('pallet', 'Pallet', 20),
            ('cft', 'Cubic Feet', 30),
            ('mt', 'Metric Tonne', 40),
            ('bin', 'Bin', 50),
        ]),
        (BillingUnit, [
            ('sqft', 'Square Feet', 10),
            ('pallet', 'Pallet', 20),
            ('cft', 'Cubic Feet', 30),
            ('mt', 'Metric Tonne', 40),
        ]),
    ]
    
    total_created = 0
    total_existing = 0
    
    print("\n  " + "="*60)
    print("  POPULATING ALL DROPDOWN MASTER DATA TABLES")
    print("  " + "="*60 + "\n")
    
    for Model, values in dropdown_data:
        model_name = Model._meta.verbose_name
        print(f"  {model_name}:")
        
        for code, label, display_order in values:
            obj, created = Model.objects.get_or_create(
                code=code,
                defaults={
                    'label': label,
                    'is_active': True,
                    'display_order': display_order,
                    'created_at': None,
                    'updated_at': None,
                    'updated_by': None,
                }
            )
            if created:
                total_created += 1
                print(f"    ✓ Created: {code}")
            else:
                total_existing += 1
                print(f"    → Exists: {code}")
    
    print("\n  " + "="*60)
    print(f"  SUMMARY: {total_created} created, {total_existing} already existed")
    print("  " + "="*60 + "\n")


def reverse_migration(apps, schema_editor):
    """Cannot reverse - data depends on these values"""
    print("  Note: Cannot reverse - data depends on these dropdown values")


class Migration(migrations.Migration):

    dependencies = [
        ('dropdown_master_data', '0003_add_required_adhoc_billing_statuses'),
    ]

    operations = [
        migrations.RunPython(
            populate_all_required_dropdown_values,
            reverse_code=reverse_migration
        ),
    ]