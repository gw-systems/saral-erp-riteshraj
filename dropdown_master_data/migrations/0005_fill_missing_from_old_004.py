# Generated manually on 2026-01-19
# Complete migration to fill ALL missing dropdown values from old 0004
# Based on comprehensive audit of all tables in staging database

from django.db import migrations


def add_all_missing_dropdown_values(apps, schema_editor):
    """
    Add ALL dropdown values that are in the updated 0004 but weren't in the original 0004,
    PLUS additional values found in data that weren't in either version.
    
    This handles staging/production where old partial 0004 was already applied.
    """
    
    # Get all required dropdown models
    TransactionSide = apps.get_model('dropdown_master_data', 'TransactionSide')
    DisputeCategory = apps.get_model('dropdown_master_data', 'DisputeCategory')
    DisputeStatus = apps.get_model('dropdown_master_data', 'DisputeStatus')
    Priority = apps.get_model('dropdown_master_data', 'Priority')
    Severity = apps.get_model('dropdown_master_data', 'Severity')
    RenewalActionType = apps.get_model('dropdown_master_data', 'RenewalActionType')
    RenewalStatus = apps.get_model('dropdown_master_data', 'RenewalStatus')
    EscalationActionType = apps.get_model('dropdown_master_data', 'EscalationActionType')
    EscalationStatus = apps.get_model('dropdown_master_data', 'EscalationStatus')
    AlertType = apps.get_model('dropdown_master_data', 'AlertType')
    ProjectStatus = apps.get_model('dropdown_master_data', 'ProjectStatus')
    MISStatus = apps.get_model('dropdown_master_data', 'MISStatus')
    OperationMode = apps.get_model('dropdown_master_data', 'OperationMode')
    HandlingBaseType = apps.get_model('dropdown_master_data', 'HandlingBaseType')
    HandlingDirection = apps.get_model('dropdown_master_data', 'HandlingDirection')
    SalesChannel = apps.get_model('dropdown_master_data', 'SalesChannel')
    StorageUnit = apps.get_model('dropdown_master_data', 'StorageUnit')
    BillingUnit = apps.get_model('dropdown_master_data', 'BillingUnit')
    VASServiceType = apps.get_model('dropdown_master_data', 'VASServiceType')
    VASUnit = apps.get_model('dropdown_master_data', 'VASUnit')
    Region = apps.get_model('dropdown_master_data', 'Region')
    SeriesType = apps.get_model('dropdown_master_data', 'SeriesType')
    ActivityType = apps.get_model('dropdown_master_data', 'ActivityType')
    OperationalCostType = apps.get_model('dropdown_master_data', 'OperationalCostType')
    
    # ALL dropdown values needed (complete comprehensive list)
    dropdown_data = [
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
            ('status_changed', 'Status Changed', 60),
        ]),
        (RenewalStatus, [
            ('pending', 'Pending', 10),
            ('approved', 'Approved', 20),
            ('in_progress', 'In Progress', 25),
            ('renewed', 'Renewed', 30),
            ('not_renewed', 'Not Renewed', 40),
            ('cancelled', 'Cancelled', 50),
        ]),
        (EscalationActionType, [
            ('email_sent', 'Email Sent', 10),
            ('call_made', 'Call Made', 20),
            ('meeting_scheduled', 'Meeting Scheduled', 30),
            ('resolved', 'Resolved', 40),
        ]),
        (EscalationStatus, [
            ('pending', 'Pending', 10),
            ('in_progress', 'In Progress', 20),
            ('resolved', 'Resolved', 30),
            ('cancelled', 'Cancelled', 40),
        ]),
        (AlertType, [
            ('info', 'Information', 10),
            ('warning', 'Warning', 20),
            ('error', 'Error', 30),
            ('critical', 'Critical', 40),
        ]),
        (ActivityType, [
            ('created', 'Created', 10),
            ('updated', 'Updated', 20),
            ('commented', 'Commented', 30),
            ('resolved', 'Resolved', 40),
            ('status_changed', 'Status Changed', 50),
        ]),
        (OperationalCostType, [
            ('equipment', 'Equipment', 10),
            ('management_fee', 'Management Fee', 20),
            ('utilities', 'Utilities', 30),
            ('other', 'Other', 40),
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
            ('per_line_item', 'Per Line Item', 25),
            ('per_order', 'Per Order', 27),
            ('per_pallet', 'Per Pallet', 30),
            ('per_roll', 'Per Roll', 35),
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
            ('rtv', 'RTV', 35),
            ('marketplace', 'Marketplace', 40),
        ]),
        (StorageUnit, [
            ('sqft', 'Square Feet', 10),
            ('pallet', 'Pallet', 20),
            ('cft', 'Cubic Feet', 30),
            ('mt', 'Metric Tonne', 40),
            ('bin', 'Bin', 50),
            ('order', 'Order', 60),
            ('lumpsum', 'Lump Sum', 70),
        ]),
        (BillingUnit, [
            ('sqft', 'Square Feet', 10),
            ('pallet', 'Pallet', 20),
            ('cft', 'Cubic Feet', 30),
            ('mt', 'Metric Tonne', 40),
        ]),
        (VASServiceType, [
            ('barcoding', 'Barcoding', 5),
            ('forklift', 'Forklift', 10),
            ('hydra', 'Hydra', 15),
            ('kitting', 'Kitting', 20),
            ('labeling', 'Labeling', 30),
            ('labelling', 'Labelling', 40),
            ('manpower', 'Manpower', 50),
            ('other', 'Other', 55),
            ('repacking', 'Repacking', 60),
        ]),
        (VASUnit, [
            ('at_actual', 'At Actual', 10),
            ('per_day', 'Per Day', 20),
            ('per_hour', 'Per Hour', 30),
            ('per_month', 'Per Month', 35),
            ('per_unit', 'Per Unit', 40),
            ('lumpsum', 'Lump Sum', 50),
        ]),
        (Region, [
            ('central', 'Central', 10),
            ('north', 'North', 20),
            ('south', 'South', 30),
            ('east', 'East', 40),
            ('west', 'West', 50),
        ]),
        (SeriesType, [
            ('WAAS', 'Warehouse as a Service', 10),
            ('SAAS', 'SaaS Only Client', 20),
            ('GW', 'Internal Use', 30),
        ]),
    ]
    
    total_created = 0
    
    print("\n  " + "="*60)
    print("  FILLING ALL MISSING DROPDOWN VALUES")
    print("  " + "="*60 + "\n")
    
    for Model, values in dropdown_data:
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
                print(f"  ✓ {Model._meta.verbose_name}: {code}")
    
    print("\n  " + "="*60)
    if total_created > 0:
        print(f"  TOTAL: {total_created} values added")
    else:
        print(f"  All values already present (0 added)")
    print("  " + "="*60 + "\n")


def reverse_migration(apps, schema_editor):
    """Cannot reverse - data depends on these values"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('dropdown_master_data', '0004_add_required_adhoc_charge_types'),
    ]

    operations = [
        migrations.RunPython(
            add_all_missing_dropdown_values,
            reverse_code=reverse_migration
        ),
    ]