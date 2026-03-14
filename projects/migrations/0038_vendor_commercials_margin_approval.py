"""
Migration: Add vendor commercial fields to QuotationItem and margin
approval fields to Quotation.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0037_projectcode_idx_pc_vendor_name_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ------------------------------------------------------------------ #
        # QuotationItem: vendor cost fields                                   #
        # ------------------------------------------------------------------ #
        migrations.AddField(
            model_name='quotationitem',
            name='vendor_unit_cost',
            field=models.CharField(
                blank=True,
                default='',
                help_text="Vendor cost per unit or 'at actual'",
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name='quotationitem',
            name='vendor_quantity',
            field=models.CharField(
                blank=True,
                default='1',
                help_text="Vendor quantity or 'as applicable'",
                max_length=50,
            ),
        ),
        # ------------------------------------------------------------------ #
        # Quotation: margin override / director approval fields               #
        # ------------------------------------------------------------------ #
        migrations.AddField(
            model_name='quotation',
            name='margin_override_requested',
            field=models.BooleanField(
                default=False,
                help_text='User requested director approval for sub-22% margin',
            ),
        ),
        migrations.AddField(
            model_name='quotation',
            name='margin_override_approved',
            field=models.BooleanField(
                default=False,
                help_text='Director approved the low-margin exception',
            ),
        ),
        migrations.AddField(
            model_name='quotation',
            name='margin_override_approved_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='approved_margin_quotations',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='quotation',
            name='margin_override_approved_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
            ),
        ),
    ]
