import logging
import math
from typing import Dict, Any, Optional

from . import zones
from .exceptions import InvalidWeightError, PincodeNotFoundError
from .models import SystemConfig


# Configure module logger
# Global settings are now fetched from SystemConfig model


class CostCalculator:
    """
    Stateful calculator to handle the complex shipping cost logic.
    Breaks down the massive calculate_cost function into manageable steps.
    """
    def __init__(self, weight: float, source_pincode: int, dest_pincode: int, 
                 carrier_data: Dict[str, Any], is_cod: bool = False, order_value: float = 0,
                 rate_type: str = "forward"):
        """
        Initialize the calculator with order and carrier details.

        Args:
            weight (float): Weight of the parcel in kg.
            source_pincode (int): Origin pincode.
            dest_pincode (int): Destination pincode.
            carrier_data (Dict[str, Any]): Dictionary containing carrier's rate card and config.
            is_cod (bool, optional): Whether payment mode is COD. Defaults to False.
            order_value (float, optional): Declared value of the shipment. Defaults to 0.
            rate_type (str, optional): 'forward' or 'reverse'. Defaults to 'forward'.
        """
        self.weight = float(weight)
        if self.weight <= 0:
            raise InvalidWeightError(self.weight)
            
        self.source_pincode = source_pincode
        self.dest_pincode = dest_pincode
        self.carrier_data = carrier_data
        self.is_cod = is_cod
        self.order_value = float(order_value)
        self.rate_type = rate_type.lower()
        
        # State extracted during calculation
        self.zone_id: Optional[str] = None
        self.zone_desc: Optional[str] = None
        self.logic_type: Optional[str] = None
        self.breakdown: Dict[str, float] = {}
        self.freight_cost: float = 0.0
        self.billing_weight: float = 0.0

        
        # Initialization
        self.max_weight: float = carrier_data.get("max_weight", 99999.0)
        self.min_weight: float = carrier_data.get("min_weight", 0)
        self.error_msg: str = ""

    def calculate(self) -> Dict[str, Any]:
        """
        Main orchestrator method for cost calculation.

        Returns:
            Dict[str, Any]: A dictionary containing total cost, breakdown, and servicability status.
        """
        # 1. Validation
        if not self._check_servicability():
            return self._error_response()
            
        # 2. Base Freight
        self._calculate_base_freight()
        
        # 3. Surcharges
        surcharges = self._calculate_surcharges()
        
        # 4. Totals & Tax
        response = self._finalize_totals(surcharges)
        return response

    def _check_servicability(self):
        """Step 1: Validate routing and constraints"""
        # Zone Lookup
        self.zone_id, self.zone_desc, self.logic_type = zones.get_zone(
            self.source_pincode, self.dest_pincode, self.carrier_data
        )
        
        if not self.zone_id:
            self.error_msg = self.zone_desc
            return False

        # Weight Limit
        if self.weight > self.max_weight:
            self.error_msg = f"Weight {self.weight}kg exceeds limit ({self.max_weight}kg)"
            return False
            
        # Source City Restriction
        required_source = self.carrier_data.get("required_source_city")
        if required_source:
             if not self._validate_source_city(required_source):
                 self.error_msg = f"Service only available from {required_source}"
                 return False
                 
        return True

    def _validate_source_city(self, required_source):
        """
        Validate source city restrictions (e.g. Bhiwandi-only carriers).
        
        For bidirectional city-specific routing (e.g., ACPL), validates that
        EITHER the source OR destination is the required hub city.
        
        Uses two methods of validation:
        1. Location database city name matching
        2. Hub pincode prefix matching (from carrier configuration)
        """
        routing_logic = self.carrier_data.get("routing_logic", {})
        is_city_specific = routing_logic.get("is_city_specific", False)
        
        # For city-specific bidirectional routing, check if EITHER endpoint is the hub
        if is_city_specific:
            source_match = self._check_city_match(self.source_pincode, required_source)
            dest_match = self._check_city_match(self.dest_pincode, required_source)
            return source_match or dest_match
        
        # For other carriers, only check source
        return self._check_city_match(self.source_pincode, required_source)
    
    def _check_city_match(self, pincode, required_city):
        """Helper to check if a pincode matches the required city."""
        loc = zones.get_location_details(pincode)
        match = False
        
        # Check 1: Location Data (city name matching)
        if loc:
             city = loc.get("city", "").lower()
             if required_city.lower() in city:
                 match = True
        
        # Check 2: Hub Pincode Prefixes (from database)
        if not match:
            hub_city = self.carrier_data.get("routing_logic", {}).get("hub_city")
            if hub_city and required_city.lower() == hub_city.lower():
                hub_prefixes = self.carrier_data.get("hub_pincode_prefixes", [])
                if hub_prefixes and isinstance(hub_prefixes, list):
                    pin_str = str(pincode)
                    for prefix in hub_prefixes:
                        if pin_str.startswith(str(prefix)):
                            match = True
                            break
                 
        return match

    def _calculate_base_freight(self):
        """Step 2: Calculate pure freight cost based on logic type"""
        routing = self.carrier_data.get("routing_logic", {})
        freight_min = self.carrier_data.get("min_freight", 0)
        
        # Model A: Per KG (City/Matrix)
        if self.logic_type in ["city_specific", "matrix"]:
            rate_per_kg = 0
            if self.logic_type == "city_specific":
                rate_per_kg = routing.get("city_rates", {}).get(self.zone_id, 0)
            elif self.logic_type == "matrix":
                origin, dest = self.zone_id
                rate_per_kg = routing.get("zonal_rates", {}).get(origin, {}).get(dest, 0)
                
            charged_weight = max(self.weight, self.min_weight)
            raw_freight = charged_weight * rate_per_kg
            self.freight_cost = max(raw_freight, freight_min)
            
            self.breakdown["rate_per_kg"] = rate_per_kg
            self.breakdown["charged_weight"] = charged_weight

        # Model B: Slab Based (Standard Zonal)
        elif self.logic_type == "standard":
            self._calculate_slab_pricing(routing)

        # Model C: CSV Region (BlueDart)
        elif self.logic_type == "pincode_region_csv":
            self._calculate_csv_pricing(freight_min)

        self.breakdown["base_freight"] = round(self.freight_cost, 2)

    def _calculate_slab_pricing(self, routing):
        """Helper for standard slab pricing"""
        slab = self.carrier_data.get("min_weight", 0.5)
        
        # Resolve rates based on rate_type
        if routing.get("zonal_rates"):
            if self.rate_type == 'reverse':
                base_rates_map = routing["zonal_rates"].get("reverse", {})
                add_rates_map = routing["zonal_rates"].get("reverse_additional", {})
            else:
                base_rates_map = routing["zonal_rates"].get("forward", {})
                add_rates_map = routing["zonal_rates"].get("additional", {})
        else:
            # Legacy fallback (less likely to be used for RVP, but safe to default)
            base_rates_map = self.carrier_data.get("forward_rates", {})
            add_rates_map = self.carrier_data.get("additional_rates", {})
        
        base_rate = base_rates_map.get(self.zone_id, 0)
        extra_rate = add_rates_map.get(self.zone_id, 0)
        
        cost = base_rate
        if self.weight > slab:
            extra_weight = self.weight - slab
            default_step = slab if slab < 1 else 1.0
            slab_step = self.carrier_data.get("weight_step", default_step)
            
            units = math.ceil(extra_weight / slab_step)
            extra_cost = units * extra_rate
            cost += extra_cost
            
            self.breakdown["extra_weight_units"] = units
            self.breakdown["extra_weight_charge"] = extra_cost
            
        self.freight_cost = cost
        self.breakdown["base_slab_rate"] = base_rate
        self.breakdown["rate_per_kg"] = base_rate # Alias for consistency
        self.breakdown["additional_rate"] = extra_rate
        self.breakdown["charged_weight"] = max(self.weight, slab)
        self.breakdown["zone"] = self.zone_desc # Ensure zone is in breakdown


    def _calculate_csv_pricing(self, freight_min):
        """Helper for CSV/Region pricing (complex edl logic)"""
        default_csv = SystemConfig.get_solo().default_servicable_csv
        csv_file = self.carrier_data.get("routing_logic", {}).get("csv_file", default_csv)
        bd_details = zones.get_csv_region_details(self.dest_pincode, csv_file)
        
        # Base Rate
        base_rate = self.carrier_data.get("forward_rates", {}).get(self.zone_id, 0)
        cost = max(self.weight, self.min_weight) * base_rate
        self.freight_cost = max(cost, freight_min)
        
        self.breakdown["base_rate_per_kg"] = base_rate
        self.breakdown["base_rate_per_kg"] = base_rate
        self.breakdown["charged_weight"] = self.weight
        self.breakdown["zone"] = self.zone_desc # Ensure zone is in breakdown
        
        # EDL Logic extracted
        edl_charge = self._calculate_edl(bd_details)
        self.breakdown["edl_charge"] = edl_charge # Always present
        if edl_charge > 0:
             pass # Already added above

    def _calculate_edl(self, bd_details):
        """Extended Delivery Location Logic"""
        if not bd_details: return 0
        
        is_edl = bd_details.get("Extended Delivery Location") == "Y"
        edl_dist_val = bd_details.get("EDL Distance")
        
        if not (is_edl and edl_dist_val):
            return 0
            
        try:
            dist = float(edl_dist_val)
            edl_config = self.carrier_data.get("edl_config", {})
            
            # 1. Special Regions
            special_regs = edl_config.get("special_regions", {})
            state = bd_details.get("STATE", "").upper().strip()
            region = bd_details.get("REGION", "").upper().strip()
            
            if state in special_regs.get("states", []) or region in special_regs.get("regions", []):
                rate = special_regs.get("rate_per_kg", 15)
                min_amt = special_regs.get("min_amount", 3000)
                return max(self.weight * rate, min_amt)

            # 2. Overflow (High dist/weight)
            overflow = edl_config.get("overflow_rates", {})
            if dist > overflow.get("dist_limit", 500) or self.weight > overflow.get("weight_limit", 1500):
                charge_a = dist * overflow.get("dist_rate_per_km", 14)
                charge_b = self.weight * overflow.get("weight_rate_per_kg", 5)
                return max(charge_a, charge_b)

            # 3. Standard Matrix
            matrix = self.carrier_data.get("edl_matrix", [])
            selected_rates = None
            for row in matrix:
                if row["dist_min"] <= dist <= row["dist_max"]:
                    selected_rates = row["rates"]
                    break
            
            if selected_rates:
                # Find Weight Slab (keys are strings "5", "10", etc)
                sorted_keys = sorted([int(k) for k in selected_rates.keys()])
                target_slab = None
                for slab_limit in sorted_keys:
                     if self.weight <= slab_limit:
                         target_slab = str(slab_limit)
                         break
                if not target_slab and sorted_keys:
                     # Above highest slab
                     target_slab = str(sorted_keys[-1])

                if target_slab:
                    return selected_rates.get(target_slab, 0)
                    
        except Exception as e:
            logger.error(f"EDL Calculation Error: {e}")
            
        return 0

    def _calculate_surcharges(self):
        """Step 3: Carrier Surcharges"""
        fixed_fees = self.carrier_data.get("fixed_fees", {})
        var_fees = self.carrier_data.get("variable_fees", {})
        
        # 1. Docket/Eway
        docket_fee = fixed_fees.get("docket_fee", 0) + fixed_fees.get("awb_fee", 0)
        eway_bill_fee = fixed_fees.get("eway_bill_fee", 0)
        
        # 2. Fuel Surcharge
        # Base for fuel includes Freight + EDL
        base_for_fuel = self.freight_cost + self.breakdown.get("edl_charge", 0)
        fuel_surcharge = self._calc_fuel(base_for_fuel)
        
        # 3. Handling
        hamali_charge = self._calc_hamali(var_fees)
        pickup_charge = self._calc_pickup_delivery(var_fees.get("pickup_slab"), is_delivery=False)
        delivery_charge = self._calc_pickup_delivery(var_fees.get("delivery_slab"), is_delivery=True)
        
        # 4. Value Added Services
        fod_charge, dod_charge = self._calc_fod_dod(var_fees)
        risk_charge, fov_charge = self._calc_risk_fov(var_fees)
        ecc_charge = self._calc_ecc(var_fees)
        cod_fee = self._calc_cod(fixed_fees, var_fees, dod_charge)

        return {
            "docket_fee": docket_fee,
            "eway_bill_fee": eway_bill_fee,
            "fuel_surcharge": fuel_surcharge,
            "hamali_charge": hamali_charge,
            "pickup_charge": pickup_charge,
            "delivery_charge": delivery_charge,
            "fod_charge": fod_charge,
            "dod_charge": dod_charge,
            "risk_charge": risk_charge,
            "fov_charge": fov_charge,
            "fov_charge": fov_charge,
            "ecc_charge": ecc_charge,
            "cod_charge": cod_fee
        }

    def _calc_fuel(self, base_amount):
        fuel_config = self.carrier_data.get("fuel_config", {})
        if fuel_config.get("is_dynamic"):
            conf = SystemConfig.get_solo()
            base_diesel = fuel_config.get("base_diesel_price", float(conf.base_diesel_price))
            diesel_ratio = fuel_config.get("diesel_ratio", float(conf.fuel_surcharge_ratio))
            current_diesel = float(conf.diesel_price_current)
            fuel_pct = (current_diesel - base_diesel) * diesel_ratio / 100
            return base_amount * fuel_pct
        else:
            return base_amount * fuel_config.get("flat_percent", 0)

    def _calc_hamali(self, var_fees):
        rate = var_fees.get("hamali_per_kg", 0)
        min_amt = var_fees.get("min_hamali", 0)
        if rate > 0 or min_amt > 0:
            return max(self.weight * rate, min_amt)
        return 0

    def _calc_pickup_delivery(self, conf, is_delivery):
        if not conf: return 0
        
        # Check exceptions for delivery
        active_conf = conf
        if is_delivery:
            dest_details = zones.get_location_details(self.dest_pincode)
            dest_city = dest_details.get("city", "").lower() if dest_details else ""
            exceptions = conf.get("city_exceptions", {})
            for city_key, c in exceptions.items():
                if city_key.lower() in dest_city:
                    active_conf = c
                    break
        
        slab_w = active_conf.get("slab", 100)
        if self.weight <= slab_w:
            return active_conf.get("base", 0)
        else:
            extra_w = self.weight - slab_w
            return active_conf.get("base", 0) + (extra_w * active_conf.get("extra_rate", 0))

    def _calc_fod_dod(self, var_fees):
        # FOD
        fod_charge = 0
        fod_conf = var_fees.get("fod_charge")
        if fod_conf:
             slab = fod_conf.get("slab_weight", 100)
             fod_charge = fod_conf.get("lte_charge", 0) if self.weight <= slab else fod_conf.get("gt_charge", 0)
             
        # DOD
        dod_charge = 0
        dod_conf = var_fees.get("dod_charge")
        if dod_conf and self.is_cod:
            dod_charge = max(self.order_value * dod_conf.get("percent", 0), dod_conf.get("min_amount", 0))
            
        return fod_charge, dod_charge

    def _calc_risk_fov(self, var_fees):
        risk_charge = 0
        fov_charge = 0
        
        # Owner's Risk (treated as Carrier Levied Charge here based on legacy logic)
        risk_conf = var_fees.get("owners_risk")
        if risk_conf and self.order_value > 0:
             risk_charge = max(self.order_value * risk_conf.get("percent", 0), risk_conf.get("min_amount", 0))
             
        # FOV - Only if risk not applied
        if not risk_charge and self.order_value > 0:
            fov_pct = var_fees.get("fov_insured_percent", 0)
            fov_min = var_fees.get("fov_min", 0)
            fov_charge = max(self.order_value * fov_pct, fov_min)
            
        return risk_charge, fov_charge

    def _calc_ecc(self, var_fees):
        ecc_conf = var_fees.get("ecc_charge")
        if ecc_conf and isinstance(ecc_conf, list):
             for slab in ecc_conf:
                 if self.weight <= slab.get("max", 999999):
                     return slab.get("charge", 0)
        return 0

    def _calc_cod(self, fixed_fees, var_fees, dod_charge):
        if not self.is_cod or dod_charge: return 0
        
        cod_fixed = fixed_fees.get("cod_fixed", 0) or self.carrier_data.get("cod_fixed", 0)
        cod_percent = var_fees.get("cod_percent", 0) or self.carrier_data.get("cod_percent", 0)
        
        if cod_percent > 1: cod_percent /= 100
        return cod_fixed + (self.order_value * cod_percent)

    def _finalize_totals(self, surcharges):
        """Step 4: Totals, Margins, Taxes"""
        
        # Base Transport
        base_transport_cost = self.freight_cost + self.breakdown.get("edl_charge", 0)
        
        # Total Surcharges
        surcharges_total = sum(surcharges.values())
        
        # Profit Margin (Escalation) - Applied only on base freight
        conf = SystemConfig.get_solo()
        escalation_rate = float(conf.escalation_rate)
        profit_margin = self.freight_cost * escalation_rate
        
        # Financials
        carrier_payable = base_transport_cost + surcharges_total
        customer_subtotal = base_transport_cost + profit_margin + surcharges_total
        
        # GST
        gst_rate = float(conf.gst_rate)
        gst_amount = customer_subtotal * gst_rate
        final_total = customer_subtotal + gst_amount
        
        # Assembly
        full_breakdown = {
            **self.breakdown,
            **{k: round(v, 2) for k, v in surcharges.items()},
            "base_transport_cost": round(base_transport_cost, 2),
            "courier_payable": round(carrier_payable, 2),
            "profit_margin": round(profit_margin, 2),
            "subtotal": round(carrier_payable, 2), # Legacy compliance
            "escalation_amount": round(profit_margin, 2),
            "amount_before_tax": round(customer_subtotal, 2),
            "gst_rate": f"{gst_rate * 100}%",
            "gst_amount": round(gst_amount, 2),
            "final_total": round(final_total, 2)
        }
        
        return {
            "carrier": self.carrier_data["carrier_name"],
            "zone_id": self.zone_id,
            "zone": self.zone_desc,
            "total_cost": round(final_total, 2),
            "breakdown": full_breakdown,
            "serviceable": True
        }

    def _error_response(self):
        return {
            "carrier": self.carrier_data["carrier_name"],
            "error": self.error_msg,
            "serviceable": False
        }



# Backward-compatible wrapper function (Adapter Pattern)
# Existing code uses this functional API. New code can use CostCalculator directly.
def calculate_cost(
    weight: float,
    source_pincode: int,
    dest_pincode: int,
    carrier_data: Dict[str, Any],
    is_cod: bool = False,
    order_value: float = 0,
    rate_type: str = "forward"
) -> Dict[str, Any]:
    """
    Calculate shipping cost for a carrier.
    
    This function provides a backward-compatible functional interface to the
    CostCalculator class. It's maintained for existing code compatibility.
    
    Args:
        weight (float): Weight in kg.
        source_pincode (int): Source Pincode.
        dest_pincode (int): Destination Pincode.
        carrier_data (Dict[str, Any]): Carrier configuration.
        is_cod (bool): Is Cash on Delivery.
        order_value (float): Value of the order.
        rate_type (str): 'forward' or 'reverse'.

    Returns:
        Dict[str, Any]: Calculation result with total_cost, breakdown, and serviceable status.
        
    Note:
        New implementations should consider using CostCalculator directly
        for better testability and clearer object-oriented design.
    """
    calculator = CostCalculator(
        weight, source_pincode, dest_pincode, carrier_data, is_cod, order_value, rate_type
    )
    return calculator.calculate()


