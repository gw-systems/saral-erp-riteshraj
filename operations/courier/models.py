from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from decimal import Decimal
from django.core.exceptions import ValidationError
from .models_refactored import FeeStructure, ServiceConstraints, FuelConfiguration, RoutingLogic


def _normalize_courier_code_text(value: str | None, fallback: str) -> str:
    normalized = slugify(str(value or "").strip())
    return normalized or fallback


def _normalize_courier_code_weight(value) -> str:
    try:
        decimal_value = Decimal(str(value))
    except Exception:
        decimal_value = Decimal("0.5")

    normalized = format(decimal_value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized.replace("-", "neg").replace(".", "p") or "0"


def build_courier_code_value(
    aggregator: str | None,
    display_name: str | None,
    service_category: str | None,
    carrier_mode: str | None,
    min_weight,
) -> str:
    """
    Build a stable, human-readable courier identity from the business identity tuple.
    """
    return "-".join(
        [
            _normalize_courier_code_text(aggregator, "generic"),
            _normalize_courier_code_text(display_name, "courier"),
            _normalize_courier_code_text(service_category, "surface"),
            _normalize_courier_code_text(carrier_mode, "surface"),
            _normalize_courier_code_weight(min_weight),
        ]
    )


class CourierManager(models.Manager):
    def create(self, **kwargs):
        # Separate legacy fields from main fields
        fees_fields = {
            'docket_fee': 'docket_fee', 
            'eway_bill_fee': 'eway_bill_fee', 
            'appointment_delivery_fee': 'appointment_delivery_fee', 
            'cod_charge_fixed': 'cod_fixed', 
            'cod_charge_percent': 'cod_percent', 
            'hamali_per_kg': 'hamali_per_kg', 
            'min_hamali': 'min_hamali', 
            'fov_min': 'fov_min', 
            'fov_insured_percent': 'fov_insured_percent', 
            'fov_uninsured_percent': 'fov_uninsured_percent', 
            'damage_claim_percent': 'damage_claim_percent'
        }
        constraints_fields = ['min_weight', 'max_weight', 'volumetric_divisor', 'required_source_city']
        fuel_fields = {'fuel_is_dynamic': 'is_dynamic', 'fuel_base_price': 'base_price', 'fuel_ratio': 'ratio', 'fuel_surcharge_percent': 'surcharge_percent'}
        routing_fields = {'rate_logic': 'logic_type', 'serviceable_pincode_csv': 'serviceable_pincode_csv', 'hub_city': 'hub_city', 'hub_pincode_prefixes': 'hub_pincode_prefixes'}
        
        fees_data = {model_k: kwargs.pop(legacy_k) for legacy_k, model_k in fees_fields.items() if legacy_k in kwargs}
        constraints_data = {k: kwargs.pop(k) for k in constraints_fields if k in kwargs}
        fuel_data = {model_k: kwargs.pop(legacy_k) for legacy_k, model_k in fuel_fields.items() if legacy_k in kwargs}
        routing_data = {model_k: kwargs.pop(legacy_k) for legacy_k, model_k in routing_fields.items() if legacy_k in kwargs}

        if not kwargs.get("courier_code"):
            kwargs["courier_code"] = build_courier_code_value(
                aggregator=kwargs.get("aggregator", Courier.Aggregator.SHIPDAAK),
                display_name=kwargs.get("display_name") or kwargs.get("name"),
                service_category=kwargs.get("service_category", Courier.ServiceCategory.SURFACE),
                carrier_mode=kwargs.get("carrier_mode", "Surface"),
                min_weight=constraints_data.get("min_weight", 0.5),
            )
        
        # Create Courier
        obj = super().create(**kwargs)
        
        # Create related components
        if fees_data or True: # always create to ensure structure exists? No, only if data. Or strict defaults.
            # Using defaults from model definition if not provided
            FeeStructure.objects.create(courier_link=obj, **fees_data)
        
        if constraints_data or True:
            ServiceConstraints.objects.create(courier_link=obj, **constraints_data)
            
        if fuel_data or True:
            FuelConfiguration.objects.create(courier_link=obj, **fuel_data)
            
        if routing_data or True:
            RoutingLogic.objects.create(courier_link=obj, **routing_data)
            
        return obj


class Courier(models.Model):
    """
    Courier model to store rate cards and configuration.
    Replaces master_card.json.
    """
    objects = CourierManager()
    
    name = models.CharField(max_length=100, unique=True, verbose_name="Carrier Name")
    is_active = models.BooleanField(default=True, verbose_name="Active")

    # Friendly Configuration Fields
    carrier_type = models.CharField(max_length=20, default="B2C", choices=[("B2C","B2C"),("B2B","B2B")])
    carrier_mode = models.CharField(max_length=20, default="Surface", choices=[("Surface","Surface"),("Air","Air")])
    
    # Aggregator Configuration
    class Aggregator(models.TextChoices):
        SHIPDAAK = "Shipdaak", "Shipdaak"
        RAPIDSHYP = "RapidShyp", "RapidShyp"
        STANDALONE = "Standalone", "Standalone" # ACPL, Blue Dart, etc.

    aggregator = models.CharField(
        max_length=50, 
        choices=Aggregator.choices, 
        default=Aggregator.SHIPDAAK,
        help_text="The aggregator providing this service."
    )
    courier_code = models.CharField(
        max_length=255,
        unique=True,
        editable=False,
        help_text=(
            "Stable immutable courier identity used for ERP/bootstrap integration. "
            "Derived from aggregator, display name, service category, carrier mode, and min weight."
        ),
    )
    
    display_name = models.CharField(
        max_length=100, 
        blank=True, 
        help_text="Clean name (e.g. 'Shadowfax'). Combined with aggregator for full name."
    )
    
    # Service Category Configuration
    class ServiceCategory(models.TextChoices):
        SURFACE = "Surface", "Surface"
        AIR = "Air", "Air"
        HEAVY_SURFACE = "Heavy Surface", "Heavy Surface"
        DOCUMENTS = "Documents", "Documents"
        NDD_SURFACE = "NDD Surface", "NDD Surface"
        NDD_HEAVY_SURFACE = "NDD Heavy Surface", "NDD Heavy Surface"
        RVP = "RVP", "RVP (Reverse Pickup)"
    
    service_category = models.CharField(
        max_length=50,
        choices=ServiceCategory.choices,
        default=ServiceCategory.SURFACE,
        help_text="Service category (Surface, Air, Heavy, Documents, NDD, RVP)"
    )
    shipdaak_courier_id = models.IntegerField(
        blank=True,
        null=True,
        db_index=True,
        help_text="Shipdaak v2 courier ID used for booking payloads.",
    )

    # --- LEGACY PROPERTIES (FACADE) ---

    def _get_fees(self):
        if not hasattr(self, 'fees_config'):
             # If accessed before save/create, this fails. 
             # But for existing objects it should work.
             return None
        return self.fees_config

    # docket_fee
    @property
    def docket_fee(self):
        return self.fees_config.docket_fee if self._get_fees() else Decimal('0.00')
    @docket_fee.setter
    def docket_fee(self, value):
        if self._get_fees(): self.fees_config.docket_fee = value; self.fees_config.save()

    # eway_bill_fee
    @property
    def eway_bill_fee(self):
        return self.fees_config.eway_bill_fee if self._get_fees() else Decimal('0.00')
    @eway_bill_fee.setter
    def eway_bill_fee(self, value):
        if self._get_fees(): self.fees_config.eway_bill_fee = value; self.fees_config.save()
    
    # ... (Implementing key properties for completeness)
    
    # min_weight
    @property
    def min_weight(self):
        return self.constraints_config.min_weight if hasattr(self, 'constraints_config') else 0.5
    @min_weight.setter
    def min_weight(self, value):
        if hasattr(self, 'constraints_config'): self.constraints_config.min_weight = value; self.constraints_config.save()

    # max_weight
    @property
    def max_weight(self):
        return self.constraints_config.max_weight if hasattr(self, 'constraints_config') else 99999.0
    @max_weight.setter
    def max_weight(self, value):
        if hasattr(self, 'constraints_config'): self.constraints_config.max_weight = value; self.constraints_config.save()

    # rate_logic (Mapped to logic_type)
    @property
    def rate_logic(self):
        return self.routing_config.logic_type if hasattr(self, 'routing_config') else "Zonal_Standard"
    @rate_logic.setter
    def rate_logic(self, value):
        if hasattr(self, 'routing_config'): self.routing_config.logic_type = value; self.routing_config.save()

    # --- Fuel Properties ---
    @property
    def fuel_is_dynamic(self):
        return self.fuel_config_obj.is_dynamic if hasattr(self, 'fuel_config_obj') else False
    @fuel_is_dynamic.setter
    def fuel_is_dynamic(self, value):
        if hasattr(self, 'fuel_config_obj'): self.fuel_config_obj.is_dynamic = value; self.fuel_config_obj.save()

    @property
    def fuel_base_price(self):
        return self.fuel_config_obj.base_price if hasattr(self, 'fuel_config_obj') else Decimal('0.00')
    @fuel_base_price.setter
    def fuel_base_price(self, value):
        if hasattr(self, 'fuel_config_obj'): self.fuel_config_obj.base_price = value; self.fuel_config_obj.save()

    @property
    def fuel_ratio(self):
        return self.fuel_config_obj.ratio if hasattr(self, 'fuel_config_obj') else Decimal('0.0000')
    @fuel_ratio.setter
    def fuel_ratio(self, value):
        if hasattr(self, 'fuel_config_obj'): self.fuel_config_obj.ratio = value; self.fuel_config_obj.save()

    @property
    def fuel_surcharge_percent(self):
        return self.fuel_config_obj.surcharge_percent if hasattr(self, 'fuel_config_obj') else Decimal('0.0000')
    @fuel_surcharge_percent.setter
    def fuel_surcharge_percent(self, value):
        if hasattr(self, 'fuel_config_obj'): self.fuel_config_obj.surcharge_percent = value; self.fuel_config_obj.save()

    # --- Other Fees Properties (Partial List for brevity, assuming standard usage covers them) ---
    @property
    def cod_charge_fixed(self): return self.fees_config.cod_fixed if self._get_fees() else Decimal('0.00')
    @cod_charge_fixed.setter
    def cod_charge_fixed(self, v): 
        if self._get_fees(): self.fees_config.cod_fixed = v; self.fees_config.save()

    @property
    def cod_charge_percent(self): return self.fees_config.cod_percent if self._get_fees() else Decimal('0.0000')
    @cod_charge_percent.setter
    def cod_charge_percent(self, v): 
        if self._get_fees(): self.fees_config.cod_percent = v; self.fees_config.save()
    
    @property
    def hamali_per_kg(self): return self.fees_config.hamali_per_kg if self._get_fees() else Decimal('0.00')
    @hamali_per_kg.setter
    def hamali_per_kg(self, v): 
        if self._get_fees(): self.fees_config.hamali_per_kg = v; self.fees_config.save()

    @property
    def min_hamali(self): return self.fees_config.min_hamali if self._get_fees() else Decimal('0.00')
    @min_hamali.setter
    def min_hamali(self, v): 
        if self._get_fees(): self.fees_config.min_hamali = v; self.fees_config.save()
        
    @property
    def appointment_delivery_fee(self): return self.fees_config.appointment_delivery_fee if self._get_fees() else Decimal('0.00')
    @appointment_delivery_fee.setter
    def appointment_delivery_fee(self, v): 
        if self._get_fees(): self.fees_config.appointment_delivery_fee = v; self.fees_config.save()

    @property
    def fov_min(self): return self.fees_config.fov_min if self._get_fees() else Decimal('0.00')
    @fov_min.setter
    def fov_min(self, v): 
        if self._get_fees(): self.fees_config.fov_min = v; self.fees_config.save()

    @property
    def fov_insured_percent(self): return self.fees_config.fov_insured_percent if self._get_fees() else Decimal('0.0000')
    @fov_insured_percent.setter
    def fov_insured_percent(self, v): 
        if self._get_fees(): self.fees_config.fov_insured_percent = v; self.fees_config.save()

    @property
    def fov_uninsured_percent(self): return self.fees_config.fov_uninsured_percent if self._get_fees() else Decimal('0.0000')
    @fov_uninsured_percent.setter
    def fov_uninsured_percent(self, v): 
        if self._get_fees(): self.fees_config.fov_uninsured_percent = v; self.fees_config.save()

    @property
    def damage_claim_percent(self): return self.fees_config.damage_claim_percent if self._get_fees() else Decimal('0.0000')
    @damage_claim_percent.setter
    def damage_claim_percent(self, v): 
        if self._get_fees(): self.fees_config.damage_claim_percent = v; self.fees_config.save()

    @property
    def other_charges(self): return self.fees_config.other_charges if self._get_fees() else Decimal('0.00')
    @other_charges.setter
    def other_charges(self, v): 
        if self._get_fees(): self.fees_config.other_charges = v; self.fees_config.save()

    # --- Routing Config Properties ---
    @property
    def serviceable_pincode_csv(self): return self.routing_config.serviceable_pincode_csv if hasattr(self, 'routing_config') else None
    @serviceable_pincode_csv.setter
    def serviceable_pincode_csv(self, v): 
        if hasattr(self, 'routing_config'): self.routing_config.serviceable_pincode_csv = v; self.routing_config.save()

    @property
    def hub_city(self): return self.routing_config.hub_city if hasattr(self, 'routing_config') else None
    @hub_city.setter
    def hub_city(self, v): 
        if hasattr(self, 'routing_config'): self.routing_config.hub_city = v; self.routing_config.save()

    @property
    def hub_pincode_prefixes(self): return self.routing_config.hub_pincode_prefixes if hasattr(self, 'routing_config') else None
    @hub_pincode_prefixes.setter
    def hub_pincode_prefixes(self, v): 
        if hasattr(self, 'routing_config'): self.routing_config.hub_pincode_prefixes = v; self.routing_config.save()
        
    @property
    def required_source_city(self): return self.constraints_config.required_source_city if hasattr(self, 'constraints_config') else None
    @required_source_city.setter
    def required_source_city(self, v):
        if hasattr(self, 'constraints_config'): self.constraints_config.required_source_city = v; self.constraints_config.save()

    @property
    def volumetric_divisor(self): return self.constraints_config.volumetric_divisor if hasattr(self, 'constraints_config') else 5000
    @volumetric_divisor.setter
    def volumetric_divisor(self, v):
        if hasattr(self, 'constraints_config'): self.constraints_config.volumetric_divisor = v; self.constraints_config.save()




    # The raw JSON - source of truth for engine, updated by fields below
    legacy_rate_card_backup = models.JSONField(help_text="Backup of legacy JSON logic", blank=True, default=dict)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'couriers'
        ordering = ['name']

    def __str__(self):
        # Format: "Aggregator - Courier - Category - Weight"
        # Example: "RapidShyp - Delhivery - Surface - 0.5kg"
        
        final_name = self.display_name or self.name
        
        # Add aggregator prefix (if not standalone)
        if self.aggregator and self.aggregator != self.Aggregator.STANDALONE:
            final_name = f"{self.aggregator} - {final_name}"
        
        # Add service category for non-default variants.
        if self.service_category and self.service_category.lower() != "surface":
            final_name = f"{final_name} - {self.service_category}"
        
        # Add min_weight
        try:
            if hasattr(self, 'constraints_config'):
                weight = float(self.constraints_config.min_weight)
                # Format weight nicely (0.5 -> 0.5kg, 1.0 -> 1kg, 10.0 -> 10kg)
                if weight == int(weight):
                    weight_str = f"{int(weight)}kg"
                else:
                    weight_str = f"{weight}kg"
                final_name = f"{final_name} - {weight_str}"
        except:
            pass
        
        return final_name

    def save(self, *args, **kwargs):
        # Removed sync logic - data source of truth is now the DB tables
        # Auto-set display_name if empty
        if not self.display_name:
            self.display_name = self.name

        if self.pk:
            existing_code = (
                Courier.objects.filter(pk=self.pk).values_list("courier_code", flat=True).first()
            )
            if existing_code:
                self.courier_code = existing_code

        if not self.courier_code:
            self.courier_code = self.build_courier_code()
        super().save(*args, **kwargs)

    @classmethod
    def build_courier_code_from_parts(
        cls,
        aggregator: str | None,
        display_name: str | None,
        service_category: str | None,
        carrier_mode: str | None,
        min_weight,
    ) -> str:
        return build_courier_code_value(
            aggregator=aggregator,
            display_name=display_name,
            service_category=service_category,
            carrier_mode=carrier_mode,
            min_weight=min_weight,
        )

    def build_courier_code(self) -> str:
        return self.build_courier_code_from_parts(
            aggregator=self.aggregator,
            display_name=self.display_name or self.name,
            service_category=self.service_category,
            carrier_mode=self.carrier_mode,
            min_weight=self.min_weight,
        )
    
    def get_rate_dict(self):
        """
        Reconstructs the dictionary expected by the engine from DB columns and CourierZoneRate.
        """
        # Fetch Zone Rates efficiently
        zone_rates = self.zone_rates.all()
        fwd_rates = {}
        add_rates = {}
        rto_rates = {}
        rto_add_rates = {}
        rev_rates = {}
        rev_add_rates = {}
        # Filter Zone Rates efficiently
        zone_rates = self.zone_rates.all()
        
        for zr in zone_rates:
            # Use robust string comparison to handle any choice mismatch
            rtype = str(zr.rate_type).lower().strip()

            
            if rtype == 'forward':
                fwd_rates[zr.zone_code] = zr.rate
            elif rtype == 'additional':
                add_rates[zr.zone_code] = zr.rate
            elif rtype == 'rto':
                rto_rates[zr.zone_code] = zr.rate
            elif rtype == 'rto_additional':
                rto_add_rates[zr.zone_code] = zr.rate
            elif rtype == 'reverse':
                rev_rates[zr.zone_code] = zr.rate
            elif rtype == 'reverse_additional':
                rev_add_rates[zr.zone_code] = zr.rate

        # --- Name Construction Logic ---
        # Format using robust __str__ logic
        final_name = self.__str__()

        data = {
            "id": self.id,
            "courier_code": self.courier_code,
            "carrier_name": final_name, # CHANGED: Uses formatted name
            "original_name": self.name, # Keep original just in case
            "type": self.carrier_type,
            "mode": self.carrier_mode,
            "service_category": self.service_category, # Critical for filtering
            "active": self.is_active,
            "min_weight": self.min_weight,
            "max_weight": self.max_weight,
            "volumetric_divisor": self.volumetric_divisor,
            "logic": "Zonal", # Default
            "required_source_city": self.required_source_city or self.legacy_rate_card_backup.get("required_source_city"), 
            "hub_pincode_prefixes": self.hub_pincode_prefixes,
            "fuel_config": {
                "is_dynamic": self.fuel_is_dynamic,
                "base_diesel_price": self.fuel_base_price,
                "diesel_ratio": self.fuel_ratio,
                "flat_percent": self.fuel_surcharge_percent
            },
            "fixed_fees": {
                "docket_fee": self.docket_fee,
                "eway_bill_fee": self.eway_bill_fee,
                "cod_fixed": self.cod_charge_fixed,
                "appointment_delivery": self.appointment_delivery_fee,
                "other_charges": getattr(self, "other_charges", 0.0)
            },
            "variable_fees": {
                "cod_percent": self.cod_charge_percent,
                "hamali_per_kg": self.hamali_per_kg,
                "min_hamali": self.min_hamali,
                "fov_insured_percent": self.fov_insured_percent,
                "fov_uninsured_percent": self.fov_uninsured_percent,
                "fov_min": self.fov_min,
                "damage_claim_percent": self.damage_claim_percent
            },
            "routing_logic": {
                "is_city_specific": False,
                "zonal_rates": {
                    "forward": fwd_rates,
                    "additional": add_rates,
                    "rto": rto_rates,
                    "rto_additional": rto_add_rates,
                    "reverse": rev_rates,
                    "reverse_additional": rev_add_rates
                },
                "city_rates": None,
                "zone_mapping": None,
                "door_delivery_slabs": []
            } 
        }

        # --- FACADE FACELIFT START ---
        # Prioritize normalized tables over legacy columns
        fees = getattr(self, 'fees_config', None)
        if fees:
            data["fixed_fees"]["docket_fee"] = fees.docket_fee
            data["fixed_fees"]["eway_bill_fee"] = fees.eway_bill_fee
            data["fixed_fees"]["cod_fixed"] = fees.cod_fixed
            data["fixed_fees"]["appointment_delivery"] = fees.appointment_delivery_fee
            data["fixed_fees"]["other_charges"] = getattr(fees, "other_charges", 0.0)
            
            data["variable_fees"]["cod_percent"] = fees.cod_percent
            data["variable_fees"]["hamali_per_kg"] = fees.hamali_per_kg
            data["variable_fees"]["min_hamali"] = fees.min_hamali
            data["variable_fees"]["fov_insured_percent"] = fees.fov_insured_percent
            data["variable_fees"]["fov_uninsured_percent"] = fees.fov_uninsured_percent
            data["variable_fees"]["fov_min"] = fees.fov_min
            data["variable_fees"]["damage_claim_percent"] = fees.damage_claim_percent

        constraints = getattr(self, 'constraints_config', None)
        if constraints:
            data["min_weight"] = constraints.min_weight
            data["max_weight"] = constraints.max_weight
            data["volumetric_divisor"] = constraints.volumetric_divisor
            data["required_source_city"] = constraints.required_source_city

        fuel = getattr(self, 'fuel_config_obj', None)
        if fuel:
            data["fuel_config"]["is_dynamic"] = fuel.is_dynamic
            data["fuel_config"]["base_diesel_price"] = fuel.base_price
            data["fuel_config"]["diesel_ratio"] = fuel.ratio
            data["fuel_config"]["flat_percent"] = fuel.surcharge_percent

        routing = getattr(self, 'routing_config', None)
        if routing:
             legacy_logic_map = {
                 "City_To_City": "city_to_city",
                 "Zonal_Standard": "Zonal",
                 "Zonal_Custom": "Zonal",
                 "Region_CSV": "pincode_region_csv"
             }
             data['logic'] = legacy_logic_map.get(routing.logic_type, 'Zonal')
        # --- FACADE FACELIFT END ---

        # Logic Mapping
        if self.rate_logic == 'City_To_City':
            data['logic'] = 'city_to_city'
            data['routing_logic']['is_city_specific'] = True
            
            # Legacy fields for zones.py logic
            if self.serviceable_pincode_csv:
                data['routing_logic']['pincode_csv'] = self.serviceable_pincode_csv
            if self.hub_city:
                data['routing_logic']['hub_city'] = self.hub_city
            
            # Populate City Rates
            city_rates = {}
            for r in self.city_routes.all():
                city_rates[r.city_name.lower()] = r.rate_per_kg
            data['routing_logic']['city_rates'] = city_rates
            
            # Populate Slabs
            slabs = []
            for s in self.delivery_slabs.all():
                slabs.append({
                    "min": s.min_weight,
                    "max": s.max_weight,
                    "rate": s.rate
                })
            data['routing_logic']['door_delivery_slabs'] = slabs
            
        elif self.rate_logic == 'Zonal_Standard':
            data['logic'] = 'Zonal'
            # Already populated via fwd_rates / add_rates above

        elif self.rate_logic == 'Zonal_Custom':
            data['logic'] = 'Zonal'
            # Zones
            zm = {}
            for z in self.custom_zones.all():
                zm[z.location_name] = z.zone_code
            data['zone_mapping'] = zm 
            
            # Rates
            zr = {}
            for r in self.custom_zone_rates.all():
                if r.from_zone not in zr: zr[r.from_zone] = {}
                zr[r.from_zone][r.to_zone] = r.rate_per_kg
            data['routing_logic']['zonal_rates'] = zr

        elif self.rate_logic == 'Region_CSV':
            data['logic'] = 'pincode_region_csv'
            # Set the type field for zones.py logic detection
            data['routing_logic']['type'] = 'pincode_region_csv'
            # Set csv_file with fallback to BlueDart default
            csv_file = self.serviceable_pincode_csv or "BlueDart_Serviceable Pincodes.csv"
            data['routing_logic']['csv_file'] = csv_file
            # Set forward_rates from CourierZoneRate table
            data['forward_rates'] = fwd_rates

        # --- LEGACY BACKUP MERGE (Global) ---
        # Merge legacy backup data (EDL config, variable fees, etc.) for ALL logic types
        # This allows injecting custom fields like 'owners_risk' that aren't in the normalized DB yet.
        if self.legacy_rate_card_backup:
            for key in ['edl_config', 'edl_matrix', 'variable_fees', 'fixed_fees']:
                if key in self.legacy_rate_card_backup:
                    if key == 'variable_fees':
                        # Merge with existing variable_fees
                        if 'variable_fees' not in data: data['variable_fees'] = {}
                        data['variable_fees'].update(self.legacy_rate_card_backup[key])
                    elif key == 'fixed_fees':
                        # Merge with existing fixed_fees
                        if 'fixed_fees' not in data: data['fixed_fees'] = {}
                        data['fixed_fees'].update(self.legacy_rate_card_backup[key])
                    else:
                        data[key] = self.legacy_rate_card_backup[key]

        def cast_decimal(obj):
            if isinstance(obj, Decimal):
                return float(obj)
            if isinstance(obj, dict):
                return {k: cast_decimal(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [cast_decimal(v) for v in obj]
            return obj

        return cast_decimal(data)

    def _sync_custom_zones_to_json(self):
        # Deprecated
        pass
        """Sync CustomZone and CustomZoneRate objects to rate_card JSON"""
        zone_mapping = {}
        for zone in self.custom_zones.all():
            zone_mapping[zone.location_name] = zone.zone_code
        
        zonal_rates = {}
        for rate in self.custom_zone_rates.all():
            if rate.from_zone not in zonal_rates:
                zonal_rates[rate.from_zone] = {}
            zonal_rates[rate.from_zone][rate.to_zone] = rate.rate_per_kg
        
        if not self.rate_card.get('routing_logic'):
            self.rate_card['routing_logic'] = {}
        self.rate_card['routing_logic']['is_city_specific'] = False
        self.rate_card['zone_mapping'] = zone_mapping
        self.rate_card['routing_logic']['zonal_rates'] = zonal_rates
        
        # Save without triggering infinite loop
        Courier.objects.filter(pk=self.pk).update(rate_card=self.rate_card)


class CityRoute(models.Model):
    """City-to-City routing rates"""
    courier = models.ForeignKey(Courier, on_delete=models.CASCADE, related_name='city_routes')
    city_name = models.CharField(max_length=100, verbose_name="City/Destination")
    rate_per_kg = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Rate (per kg)")
    
    class Meta:
        db_table = 'city_routes'
        unique_together = ['courier', 'city_name']
        ordering = ['city_name']
    
    def __str__(self):
        return f"{self.courier.name} - {self.city_name}"


class DeliverySlab(models.Model):
    """Delivery slabs for City-to-City logic"""
    courier = models.ForeignKey(Courier, on_delete=models.CASCADE, related_name='delivery_slabs')
    min_weight = models.FloatField(verbose_name="Min Weight")
    max_weight = models.FloatField(verbose_name="Max Weight", null=True, blank=True)
    rate = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Flat Rate")
    
    class Meta:
        db_table = 'delivery_slabs'
        ordering = ['min_weight']
    
    def __str__(self):
        return f"{self.courier.name}: {self.min_weight}-{self.max_weight} = {self.rate}"


class CustomZone(models.Model):
    """Custom zone mapping (location to zone code)"""
    courier = models.ForeignKey(Courier, on_delete=models.CASCADE, related_name='custom_zones')
    location_name = models.CharField(max_length=100, help_text="State/City/Region name")
    zone_code = models.CharField(max_length=20, help_text="Zone code (e.g. CTL, E1, MH1)")
    
    class Meta:
        db_table = 'custom_zones'
        unique_together = ['courier', 'location_name']
        ordering = ['zone_code', 'location_name']
    
    def __str__(self):
        return f"{self.location_name} → {self.zone_code}"


class CustomZoneRate(models.Model):
    """Custom zone matrix rates (from zone to zone)"""
    courier = models.ForeignKey(Courier, on_delete=models.CASCADE, related_name='custom_zone_rates')
    from_zone = models.CharField(max_length=20, verbose_name="From Zone")
    to_zone = models.CharField(max_length=20, verbose_name="To Zone")
    rate_per_kg = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Rate (per kg)")
    
    class Meta:
        db_table = 'custom_zone_rates'
        unique_together = ['courier', 'from_zone', 'to_zone']
        ordering = ['from_zone', 'to_zone']
    
    def __str__(self):
        return f"{self.from_zone} → {self.to_zone}: ₹{self.rate_per_kg}"


class Warehouse(models.Model):
    """Courier-only warehouse and Shipdaak sync metadata."""

    name = models.CharField(max_length=150)
    contact_name = models.CharField(max_length=150)
    contact_no = models.CharField(max_length=20)
    address = models.TextField()
    address_2 = models.TextField(blank=True, null=True)
    pincode = models.CharField(max_length=10)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    gst_number = models.CharField(max_length=30, blank=True, null=True)

    shipdaak_pickup_id = models.IntegerField(blank=True, null=True)
    shipdaak_rto_id = models.IntegerField(blank=True, null=True)
    shipdaak_synced_at = models.DateTimeField(blank=True, null=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "warehouses"
        ordering = ["name"]
        verbose_name = "Courier Warehouse"
        verbose_name_plural = "Courier Warehouses"

    def __str__(self):
        return f"{self.name} (Courier Warehouse)"


class OrderStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    BOOKED = "booked", "Booked / Ready to Ship"
    MANIFESTED = "manifested", "Manifested"
    PICKED_UP = "picked_up", "Picked Up / In Transit"
    OUT_FOR_DELIVERY = "out_for_delivery", "Out for Delivery"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled / Unbooked"
    PICKUP_EXCEPTION = "pickup_exception", "Pickup Exception"
    NDR = "ndr", "NDR (Non-Delivery Report)"
    RTO = "rto", "RTO (Return to Origin)"


class PaymentMode(models.TextChoices):
    COD = "cod", "Cash on Delivery"
    PREPAID = "prepaid", "Prepaid"


class Order(models.Model):
    """
    Order model for logistics management.
    Converted from SQLAlchemy to Django ORM.
    """
    # Auto-generated fields
    id = models.BigAutoField(primary_key=True)
    order_number = models.CharField(max_length=50, unique=True, db_index=True)
    external_order_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text="External WMS order ID used by Shipdaak v2 booking.",
    )

    # Recipient Details
    recipient_name = models.CharField(max_length=255)
    recipient_contact = models.CharField(max_length=15)  # Mandatory contact number
    recipient_address = models.TextField()
    recipient_pincode = models.IntegerField()
    recipient_city = models.CharField(max_length=100, blank=True, null=True)  # Auto-filled
    recipient_state = models.CharField(max_length=100, blank=True, null=True)  # Auto-filled
    recipient_phone = models.CharField(max_length=15, blank=True, null=True)
    recipient_email = models.EmailField(blank=True, null=True)

    # Sender Details
    sender_pincode = models.IntegerField()
    sender_name = models.CharField(max_length=255, blank=True, null=True)
    sender_address = models.TextField(blank=True, null=True)
    sender_phone = models.CharField(max_length=15, blank=True, null=True)

    # Box Details
    weight = models.FloatField()  # Actual weight in kg
    length = models.FloatField()  # Length in cm (mandatory)
    width = models.FloatField()   # Width in cm (mandatory)
    height = models.FloatField()  # Height in cm (mandatory)
    volumetric_weight = models.FloatField(blank=True, null=True)  # Calculated: (L x W x H) / 5000
    applicable_weight = models.FloatField(blank=True, null=True)  # max(actual_weight, volumetric_weight)

    # Payment
    payment_mode = models.CharField(
        max_length=10,
        choices=PaymentMode.choices,
        default=PaymentMode.PREPAID
    )
    order_value = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        help_text="Order value for COD"
    )

    # Items Info
    item_type = models.CharField(max_length=100, blank=True, null=True)
    sku = models.CharField(max_length=100, blank=True, null=True)
    quantity = models.IntegerField(default=1)
    item_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        help_text="Item amount"
    )

    # Order Status & Tracking
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.DRAFT
    )

    # Shipment Details (filled after carrier selection)
    carrier = models.ForeignKey('Courier', on_delete=models.PROTECT, null=True, blank=True, related_name='orders')
    warehouse = models.ForeignKey(
        'Warehouse',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='orders',
        verbose_name='Courier Warehouse',
        help_text='Courier-only warehouse used for courier booking and ShipDaak sync.',
    )
    total_cost = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True,
        help_text="Total shipping cost"
    )
    cost_breakdown = models.JSONField(blank=True, null=True)  # Stores the full breakdown
    awb_number = models.CharField(max_length=100, blank=True, null=True)  # Air Waybill number
    shipdaak_order_id = models.IntegerField(
        blank=True,
        null=True,
        help_text="ShipDaak orderId set when the order is registered in ShipDaak (before AWB).",
    )
    shipdaak_shipment_id = models.CharField(max_length=100, blank=True, null=True)
    shipdaak_label_url = models.URLField(max_length=500, blank=True, null=True)
    zone_applied = models.CharField(max_length=100, blank=True, null=True)
    mode = models.CharField(max_length=20, blank=True, null=True)  # Surface/Air

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    booked_at = models.DateTimeField(blank=True, null=True)

    # Additional metadata
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order_number']),
            models.Index(fields=['external_order_id']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.order_number} - {self.recipient_name}"

    def save(self, *args, **kwargs):
        # Determine volumetric divisor
        divisor = 5000
        if self.carrier:
            divisor = self.carrier.volumetric_divisor

        # Calculate volumetric weight if dimensions are provided
        if self.length and self.width and self.height:
            self.volumetric_weight = (self.length * self.width * self.height) / divisor
            self.applicable_weight = max(self.weight, self.volumetric_weight)
        else:
            self.applicable_weight = self.weight

        super().save(*args, **kwargs)


class FTLOrder(models.Model):
    """
    Full Truck Load (FTL) Order model.
    Different from regular courier orders - uses container-based pricing.
    """
    # Auto-generated fields
    id = models.BigAutoField(primary_key=True)
    order_number = models.CharField(max_length=50, unique=True, db_index=True)

    # Contact Details
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=15)

    # Location Details
    source_city = models.CharField(max_length=100)
    source_address = models.TextField(blank=True, null=True)
    source_pincode = models.IntegerField()
    destination_city = models.CharField(max_length=100)
    destination_address = models.TextField(blank=True, null=True)
    destination_pincode = models.IntegerField()

    # Container Details
    container_type = models.CharField(
        max_length=20,
        choices=[
            ("20FT", "20FT"),
            ("32 FT SXL 7MT", "32 FT SXL 7MT"),
            ("32 FT SXL 9MT", "32 FT SXL 9MT"),
        ]
    )

    # Pricing Details
    base_price = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Base price before escalation"
    )
    escalation_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="15% of base price"
    )
    price_with_escalation = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Base + escalation"
    )
    gst_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="18% GST on price_with_escalation"
    )
    total_price = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Final total price"
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.DRAFT
    )
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    booked_at = models.DateTimeField(blank=True, null=True)

    # Additional metadata
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'ftl_orders'
        ordering = ['-created_at']


class FTLRate(models.Model):
    """
    Store FTL Rates in DB mainly for management via Admin.
    Replaces ftl_rates.json
    """
    source_city = models.CharField(max_length=100, db_index=True)
    destination_city = models.CharField(max_length=100, db_index=True)
    truck_type = models.CharField(
        max_length=50,
        choices=[
            ("20FT", "20FT"),
            ("32 FT SXL 7MT", "32 FT SXL 7MT"),
            ("32 FT SXL 9MT", "32 FT SXL 9MT"),
        ]
    )
    rate = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Rate (₹)")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ftl_rates'
        unique_together = ['source_city', 'destination_city', 'truck_type']
        ordering = ['source_city', 'destination_city']
        verbose_name = "FTL Rate"
        verbose_name_plural = "FTL Rates"

    def __str__(self):
        return f"{self.source_city} -> {self.destination_city} ({self.truck_type}): ₹{self.rate}"



class SystemConfig(models.Model):
    """
    Singleton-like model to store global system configuration.
    Replaces settings.json and hardcoded values.
    """
    # Fuel Config
    diesel_price_current = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('90.00'),
        verbose_name="Current Diesel Price", help_text="Used for dynamic fuel surcharge calculation"
    )
    base_diesel_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('90.00'),
        verbose_name="Base Diesel Price", help_text="Benchmark price for fuel surcharge"
    )
    fuel_surcharge_ratio = models.DecimalField(
        max_digits=5, decimal_places=3, default=Decimal('0.625'),
        verbose_name="Fuel Surcharge Ratio", help_text="Ratio for fuel surcharge calculation"
    )

    # Financial Config
    gst_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.18'),
        verbose_name="GST Rate", help_text="18% = 0.18"
    )
    escalation_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.15'),
        verbose_name="Escalation Rate", help_text="Margin/Escalation 15% = 0.15"
    )

    # File/Path Config
    default_servicable_csv = models.CharField(
        max_length=255, default="BlueDart_Servicable Pincodes.csv",
        verbose_name="Default Serviceable CSV", help_text="Filename in config directory"
    )

    class Meta:
        db_table = 'system_config'
        verbose_name = "System Configuration"
        verbose_name_plural = "System Configuration"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(pk=1),
                name="system_config_singleton_pk_1",
            ),
        ]

    def __str__(self):
        return "Global System Configuration"

    def save(self, *args, **kwargs):
        if self.pk is None:
            self.pk = 1
        elif self.pk != 1:
            raise ValidationError("SystemConfig is a singleton and must have primary key = 1.")
        return super().save(*args, **kwargs)

    @classmethod

    def get_solo(cls):
        """Get the configuration object, creating if it doesn't exist."""
        obj, created = cls.objects.get_or_create(pk=1)
        return obj


class CourierZoneRate(models.Model):
    """
    Normalized model to store Forward and Additional rates per zone.
    Replaces fwd_z_a, add_z_b, etc. columns on Courier model.
    """
    class RateType(models.TextChoices):
        FORWARD = "forward", "Forward Rate"
        ADDITIONAL = "additional", "Additional Rate"
        RTO = "rto", "RTO Rate"
        RTO_ADDITIONAL = "rto_additional", "RTO Additional Rate"
        REVERSE = "reverse", "Reverse Rate"
        REVERSE_ADDITIONAL = "reverse_additional", "Reverse Additional Rate"

    courier = models.ForeignKey(Courier, on_delete=models.CASCADE, related_name='zone_rates')
    zone_code = models.CharField(max_length=20, help_text="Zone Code (e.g. z_a, z_b, north, south)")
    rate_type = models.CharField(max_length=20, choices=RateType.choices, default=RateType.FORWARD)
    rate = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Rate (₹)")
    
    class Meta:
        db_table = 'courier_zone_rates'
        unique_together = ['courier', 'zone_code', 'rate_type']
        ordering = ['zone_code', 'rate_type']

    def __str__(self):
        return f"{self.courier.name} - {self.zone_code} ({self.rate_type}): ₹{self.rate}"


class Pincode(models.Model):
    """
    Master Pincode Database.
    Replaces pincode_master.csv
    """
    pincode = models.IntegerField(primary_key=True)
    office_name = models.CharField(max_length=100, db_index=True)
    pincode_type = models.CharField(max_length=50, blank=True, null=True) # e.g. B.O, S.O
    district = models.CharField(max_length=100, db_index=True)
    state = models.CharField(max_length=100, db_index=True)
    
    # Metadata for potential validation
    is_serviceable = models.BooleanField(default=True)

    class Meta:
        db_table = 'pincode_master'
        indexes = [
            models.Index(fields=['state', 'district']),
        ]

    def __str__(self):
        return f"{self.pincode} - {self.office_name}"


class ServiceablePincode(models.Model):
    """
    Carrier-specific Serviceable Pincodes & Regions.
    Replaces BlueDart_Serviceable Pincodes.csv and other carrier CSVs.
    """
    courier = models.ForeignKey(Courier, on_delete=models.CASCADE, related_name='serviceable_pincodes')
    pincode = models.IntegerField(db_index=True)
    
    # Generic Region/Zone Identifier (e.g. "NORTH", "Z1")
    region_code = models.CharField(max_length=50, blank=True, null=True)
    
    # Extended Delivery Location (EDL) Data
    is_edl = models.BooleanField(default=False)
    edl_distance = models.FloatField(default=0.0, help_text="Distance for EDL calculation")
    
    # Service Flags
    is_cod_available = models.BooleanField(default=True)
    is_prepaid_available = models.BooleanField(default=True)
    is_pickup_available = models.BooleanField(default=True)
    is_embargo = models.BooleanField(default=False, help_text="If true, service is blocked (embargo)")
    
    # City mapping (for ACPL, etc.)
    city_name = models.CharField(max_length=100, blank=True, null=True, help_text="Mapped City for City-to-City logic")

    class Meta:
        db_table = 'serviceable_pincodes'
        unique_together = ['courier', 'pincode']
        indexes = [
            models.Index(fields=['courier', 'pincode']),
            models.Index(fields=['courier', 'city_name']),
        ]

    def __str__(self):
        return f"{self.courier.name} - {self.pincode} ({self.region_code})"


class ZoneRule(models.Model):
    """
    Configuration for Zone logic (replacing metro_cities.json, special_states.json).
    """
    class RuleType(models.TextChoices):
        METRO_CITY = "metro_city", "Metro City (Zone A)"
        SPECIAL_STATE = "special_state", "Special State (Zone E)"
        
    name = models.CharField(max_length=100, help_text="City or State name (lowercase)")
    rule_type = models.CharField(max_length=50, choices=RuleType.choices)
    
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'zone_rules'
        unique_together = ['name', 'rule_type']
        verbose_name = "Zone Rule"
        verbose_name_plural = "Zone Rules (Metros & Special States)"
        
    def __str__(self):
        return f"{self.name} ({self.get_rule_type_display()})"
    
    def save(self, *args, **kwargs):
        self.name = self.name.lower().strip()
        super().save(*args, **kwargs)


class LocationAlias(models.Model):
    """
    Normalization mapping for Cities and States.
    Replaces alias_map.json
    """
    class AliasCategory(models.TextChoices):
        CITY = "city", "City"
        STATE = "state", "State"
        
    alias = models.CharField(max_length=100, db_index=True, help_text="The variation (e.g. 'blr', 'bombay')")
    standard_name = models.CharField(max_length=100, help_text="The standard name (e.g. 'bangalore', 'mumbai')")
    category = models.CharField(max_length=50, choices=AliasCategory.choices)
    
    class Meta:
        db_table = 'location_aliases'
        unique_together = ['alias', 'category']
        verbose_name = "Location Alias"
        verbose_name_plural = "Location Aliases"
        indexes = [
            models.Index(fields=['alias', 'category']),
        ]
        
    def __str__(self):
        return f"{self.category}: {self.alias} -> {self.standard_name}"
    
    def save(self, *args, **kwargs):
        self.alias = self.alias.lower().strip()
        self.standard_name = self.standard_name.lower().strip()
        super().save(*args, **kwargs)
