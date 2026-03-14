from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrate_old_data_to_line_items(apps, schema_editor):
    """Convert old single-line entries to new multi-line structure"""
    AdhocBillingEntry = apps.get_model('operations', 'AdhocBillingEntry')
    AdhocBillingLineItem = apps.get_model('operations', 'AdhocBillingLineItem')
    
    entries = AdhocBillingEntry.objects.all()
    
    for entry in entries:
        # Migrate client side
        client_amt = getattr(entry, 'client_amount', None)
        if client_amt and client_amt > 0:
            AdhocBillingLineItem.objects.create(
                entry=entry,
                side='client',
                charge_type=getattr(entry, 'charge_type', 'other') or 'other',
                description=getattr(entry, 'description', 'Migrated from old entry') or 'Migrated from old entry',
                quantity=getattr(entry, 'client_quantity', 1) or 1,
                rate=getattr(entry, 'client_rate', client_amt) or client_amt,
                unit=getattr(entry, 'unit', 'unit') or 'unit',
                amount=client_amt
            )
        
        # Migrate vendor side
        vendor_amt = getattr(entry, 'vendor_amount', None)
        if vendor_amt and vendor_amt > 0:
            AdhocBillingLineItem.objects.create(
                entry=entry,
                side='vendor',
                charge_type=getattr(entry, 'charge_type', 'other') or 'other',
                description=getattr(entry, 'description', 'Migrated from old entry') or 'Migrated from old entry',
                quantity=getattr(entry, 'vendor_quantity', 1) or 1,
                rate=getattr(entry, 'vendor_rate', vendor_amt) or vendor_amt,
                unit=getattr(entry, 'unit', 'unit') or 'unit',
                amount=vendor_amt
            )
        
        # Update totals
        entry.total_client_amount = client_amt or 0
        entry.total_vendor_amount = vendor_amt or 0
        entry.save(update_fields=['total_client_amount', 'total_vendor_amount'])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('operations', '0028_projectcard_client_card_projectcard_vendor_warehouse_and_more'),
    ]

    operations = [
        # STEP 1: Add new total fields to AdhocBillingEntry
        migrations.AddField(
            model_name='adhocbillingentry',
            name='total_client_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15),
        ),
        migrations.AddField(
            model_name='adhocbillingentry',
            name='total_vendor_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15),
        ),
        
        # STEP 2: Create AdhocBillingLineItem model
        migrations.CreateModel(
            name='AdhocBillingLineItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('side', models.CharField(choices=[('client', 'Client (Receivable)'), ('vendor', 'Vendor (Payable)')], max_length=10)),
                ('charge_type', models.CharField(choices=[
                    ('extra_storage', 'Extra Storage Space'),
                    ('extra_manpower', 'Extra Manpower'),
                    ('extra_handling', 'Extra Handling Charges'),
                    ('overtime', 'Overtime'),
                    ('vas', 'Value Added Services'),
                    ('transport', 'Transport Charges'),
                    ('equipment', 'Equipment Rental'),
                    ('other', 'Other')
                ], max_length=20)),
                ('description', models.TextField()),
                ('quantity', models.DecimalField(decimal_places=2, max_digits=10)),
                ('rate', models.DecimalField(decimal_places=2, max_digits=10)),
                ('unit', models.CharField(help_text='e.g., per person, per sq.ft., per box', max_length=50)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=15)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('entry', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='line_items', to='operations.adhocbillingentry')),
            ],
            options={
                'verbose_name': 'Adhoc Billing Line Item',
                'verbose_name_plural': 'Adhoc Billing Line Items',
                'ordering': ['id'],
            },
        ),
        
        # STEP 3: Migrate existing data to line items
        migrations.RunPython(migrate_old_data_to_line_items, reverse_code=migrations.RunPython.noop),
        
        # STEP 4: Remove old fields from AdhocBillingEntry
        migrations.RemoveField(
            model_name='adhocbillingentry',
            name='client_quantity',
        ),
        migrations.RemoveField(
            model_name='adhocbillingentry',
            name='client_rate',
        ),
        migrations.RemoveField(
            model_name='adhocbillingentry',
            name='client_amount',
        ),
        migrations.RemoveField(
            model_name='adhocbillingentry',
            name='vendor_quantity',
        ),
        migrations.RemoveField(
            model_name='adhocbillingentry',
            name='vendor_rate',
        ),
        migrations.RemoveField(
            model_name='adhocbillingentry',
            name='vendor_amount',
        ),
        migrations.RemoveField(
            model_name='adhocbillingentry',
            name='charge_type',
        ),
        migrations.RemoveField(
            model_name='adhocbillingentry',
            name='description',
        ),
        migrations.RemoveField(
            model_name='adhocbillingentry',
            name='unit',
        ),
    ]