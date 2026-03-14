# Generated migration for document field changes

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0020_add_temp_project_support'),
    ]

    operations = [
        # Client Documents - Convert URLField to FileField
        migrations.AlterField(
            model_name='clientdocument',
            name='client_doc_certificate_of_incorporation_link',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='client_documents/%Y/%m/',
                verbose_name='Certificate of Incorporation'
            ),
        ),
        migrations.RenameField(
            model_name='clientdocument',
            old_name='client_doc_certificate_of_incorporation_link',
            new_name='client_doc_certificate_of_incorporation',
        ),
        
        migrations.AlterField(
            model_name='clientdocument',
            name='client_doc_board_resolution_link',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='client_documents/%Y/%m/',
                verbose_name='Board Resolution'
            ),
        ),
        migrations.RenameField(
            model_name='clientdocument',
            old_name='client_doc_board_resolution_link',
            new_name='client_doc_board_resolution',
        ),
        
        migrations.AlterField(
            model_name='clientdocument',
            name='client_doc_authorized_signatory_link',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='client_documents/%Y/%m/',
                verbose_name='Authorized Signatory Details'
            ),
        ),
        migrations.RenameField(
            model_name='clientdocument',
            old_name='client_doc_authorized_signatory_link',
            new_name='client_doc_authorized_signatory',
        ),
        
        # Warehouse Documents - Convert URLField to FileField
        migrations.AlterField(
            model_name='vendorwarehousedocument',
            name='warehouse_electricity_bill_link',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='warehouse_documents/%Y/%m/',
                verbose_name='Electricity Bill'
            ),
        ),
        migrations.RenameField(
            model_name='vendorwarehousedocument',
            old_name='warehouse_electricity_bill_link',
            new_name='warehouse_electricity_bill',
        ),
        
        migrations.AlterField(
            model_name='vendorwarehousedocument',
            name='warehouse_property_tax_receipt_link',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='warehouse_documents/%Y/%m/',
                verbose_name='Property Tax Receipt'
            ),
        ),
        migrations.RenameField(
            model_name='vendorwarehousedocument',
            old_name='warehouse_property_tax_receipt_link',
            new_name='warehouse_property_tax_receipt',
        ),
        
        migrations.AlterField(
            model_name='vendorwarehousedocument',
            name='warehouse_poc_aadhar_link',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='warehouse_documents/%Y/%m/',
                verbose_name='POC Aadhar Card'
            ),
        ),
        migrations.RenameField(
            model_name='vendorwarehousedocument',
            old_name='warehouse_poc_aadhar_link',
            new_name='warehouse_poc_aadhar',
        ),
        
        migrations.AlterField(
            model_name='vendorwarehousedocument',
            name='warehouse_poc_pan_link',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='warehouse_documents/%Y/%m/',
                verbose_name='POC PAN Card'
            ),
        ),
        migrations.RenameField(
            model_name='vendorwarehousedocument',
            old_name='warehouse_poc_pan_link',
            new_name='warehouse_poc_pan',
        ),
        
        migrations.AlterField(
            model_name='vendorwarehousedocument',
            name='warehouse_noc_owner_link',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='warehouse_documents/%Y/%m/',
                verbose_name='NOC from Owner'
            ),
        ),
        migrations.RenameField(
            model_name='vendorwarehousedocument',
            old_name='warehouse_noc_owner_link',
            new_name='warehouse_noc_owner',
        ),
        
        migrations.AlterField(
            model_name='vendorwarehousedocument',
            name='warehouse_owner_pan_link',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='warehouse_documents/%Y/%m/',
                verbose_name='Owner PAN Card'
            ),
        ),
        migrations.RenameField(
            model_name='vendorwarehousedocument',
            old_name='warehouse_owner_pan_link',
            new_name='warehouse_owner_pan',
        ),
        
        migrations.AlterField(
            model_name='vendorwarehousedocument',
            name='warehouse_owner_aadhar_link',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='warehouse_documents/%Y/%m/',
                verbose_name='Owner Aadhar Card'
            ),
        ),
        migrations.RenameField(
            model_name='vendorwarehousedocument',
            old_name='warehouse_owner_aadhar_link',
            new_name='warehouse_owner_aadhar',
        ),
        
        migrations.AlterField(
            model_name='vendorwarehousedocument',
            name='warehouse_noc_vendor_link',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='warehouse_documents/%Y/%m/',
                verbose_name='NOC from Vendor'
            ),
        ),
        migrations.RenameField(
            model_name='vendorwarehousedocument',
            old_name='warehouse_noc_vendor_link',
            new_name='warehouse_noc_vendor',
        ),
    ]