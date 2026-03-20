from django.db import models
from decimal import Decimal

class FeeStructure(models.Model):
    """Normalized table for all fixed and variable fees."""
    # Fixed Fees
    docket_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Docket Fee")
    eway_bill_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="E-Way Bill Fee")
    appointment_delivery_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Appointment Delivery Fee")
    
    # COD Fees
    cod_fixed = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="COD Fixed Fee")
    cod_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal('0.0000'), verbose_name="COD %")
    
    # Variable Fees
    hamali_per_kg = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Hamali (per kg)")
    min_hamali = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Min Hamali")
    fov_min = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Min FOV")
    fov_insured_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal('0.0000'), verbose_name="FOV Insured %")
    fov_uninsured_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal('0.0000'), verbose_name="FOV Uninsured %")
    damage_claim_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal('0.0000'), verbose_name="Damage Claim %")
    other_charges = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Other Charges")
    
    courier_link = models.OneToOneField('courier.Courier', on_delete=models.CASCADE, related_name='fees_config', null=True, blank=True)

    class Meta:
        app_label = 'courier'
        db_table = 'courier_fee_structures'

class ServiceConstraints(models.Model):
    """Normalized table for weight limits and basic constraints."""
    min_weight = models.FloatField(default=0.5, help_text="Min weight in kg")
    max_weight = models.FloatField(default=99999.0, help_text="Max weight in kg")
    volumetric_divisor = models.IntegerField(default=5000)
    required_source_city = models.CharField(max_length=100, blank=True, null=True)

    courier_link = models.OneToOneField('courier.Courier', on_delete=models.CASCADE, related_name='constraints_config', null=True, blank=True)

    class Meta:
        app_label = 'courier'
        db_table = 'courier_service_constraints'

class FuelConfiguration(models.Model):
    """Normalized fuel surcharge configuration."""
    is_dynamic = models.BooleanField(default=False)
    base_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    ratio = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal('0.0000'))
    surcharge_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal('0.0000'), verbose_name="Flat Surcharge %")

    courier_link = models.OneToOneField('courier.Courier', on_delete=models.CASCADE, related_name='fuel_config_obj', null=True, blank=True)

    class Meta:
        app_label = 'courier'
        db_table = 'courier_fuel_configs'

class RoutingLogic(models.Model):
    """Configuration for routing logic (CSV, Zonal, etc)."""
    logic_type = models.CharField(
        max_length=20, 
        choices=[
            ("Zonal_Standard","Zonal (Standard A-F)"),
            ("Zonal_Custom","Zonal (Custom Matrix)"),
            ("City_To_City","City to City"),
            ("Region_CSV","Regional CSV")
        ],
        default="Zonal_Standard"
    )
    serviceable_pincode_csv = models.CharField(max_length=255, blank=True, null=True)
    hub_city = models.CharField(max_length=100, blank=True, null=True)
    hub_pincode_prefixes = models.JSONField(blank=True, null=True)  # Still JSON for now, can normalize later

    courier_link = models.OneToOneField('courier.Courier', on_delete=models.CASCADE, related_name='routing_config', null=True, blank=True)

    class Meta:
        app_label = 'courier'
        db_table = 'courier_routing_logics'
