import logging
from .models import Pincode, ServiceablePincode, ZoneRule

# Configure module logger
logger = logging.getLogger('courier')

# Keep Alias Map for now (Step 3) - Removed but we need cache
from django.core.cache import cache
from .models import LocationAlias

def get_alias_map():
    """
    Load all alias mappings from DB (cached).
    Returns: {'city': {alias: standard}, 'state': {alias: standard}}
    """
    CACHE_KEY = 'location_alias_map'
    alias_map = cache.get(CACHE_KEY)
    
    if alias_map is None:
        alias_map = {
            'city': {},
            'state': {}
        }
        try:
            qs = LocationAlias.objects.all()
            for obj in qs:
                # Store alias -> standard mapping
                if obj.category == LocationAlias.AliasCategory.CITY:
                    alias_map['city'][obj.alias] = obj.standard_name
                elif obj.category == LocationAlias.AliasCategory.STATE:
                    alias_map['state'][obj.alias] = obj.standard_name
            
            cache.set(CACHE_KEY, alias_map, 300) # 5 min cache
        except Exception as e:
            logger.error(f"Error loading LocationAlias: {e}")
            
    return alias_map

def normalize_name(name: str, type: str = 'state') -> str:
    """
    Normalizes City/State names using LocationAlias (DB).
    Ex: 'Gujarat' -> 'gujrat' (if mapped) or 'gujrat' -> 'gujarat'
    Note: The original logic in alias_map.json was somewhat ambiguous:
         "gujarat": ["gujrat"] meant if input is "gujrat" -> return "gujarat".
         
    This function should return the STANDARD name if the input matches an alias.
    """
    cleaned = str(name).lower().replace("&", "and").strip()
    
    # Determine category key
    cat_key = 'state'
    if type == 'city' or type == 'cities':
        cat_key = 'city'
        
    alias_map = get_alias_map()  # returns {alias: standard}
    section = alias_map.get(cat_key, {})
    
    # Check if cleaned name IS an alias
    if cleaned in section:
        return section[cleaned]
        
    # Check if cleaned name IS a standard name (reverse lookup optimization or just return as is)
    # If it's not an alias, we assume it's either already standard or unknown.
    # We return it as is.
    
    return cleaned

def get_location_details(pincode: int):
    """
    Fetch location details from Pincode model (DB).
    Replaces in-memory dict lookup.
    """
    try:
        data = Pincode.objects.get(pincode=pincode)
        return {
            "city": normalize_name(data.office_name, "city"),
            "state": normalize_name(data.state, "state"),
            "district": normalize_name(data.district, "city"),
            "original_city": str(data.office_name).lower().strip(),
            "original_state": str(data.state).lower().strip()
        }
    except Pincode.DoesNotExist:
        return None
    except Exception as e:
        logger.error(f"Error fetching pincode {pincode}: {e}")
        return None

def get_zone_rules():
    """
    Load all active zone rules from DB (cached).
    Returns: {'metro_cities': set(), 'special_states': set()}
    """
    CACHE_KEY = 'zone_rules_config'
    rules = cache.get(CACHE_KEY)
    
    if rules is None:
        rules = {
            'metro_cities': set(),
            'special_states': set()
        }
        try:
            qs = ZoneRule.objects.filter(is_active=True)
            for obj in qs:
                if obj.rule_type == ZoneRule.RuleType.METRO_CITY:
                    rules['metro_cities'].add(obj.name)
                elif obj.rule_type == ZoneRule.RuleType.SPECIAL_STATE:
                    rules['special_states'].add(obj.name)
            
            cache.set(CACHE_KEY, rules, 300) # 5 min cache
        except Exception as e:
            logger.error(f"Error loading ZoneRules: {e}")
            
    return rules

def is_metro(location_dict):
    rules = get_zone_rules()
    city = location_dict["city"]
    district = location_dict["district"]
    
    metros = rules['metro_cities']
    
    # Original logic was substring match (e.g. "delhi" in "new delhi")
    # We must preserve this behavior as Pincode data is messy.
    for metro in metros:
        if metro in city or metro in district:
            return True
            
    # Debug logging for test failures
    # logger.info(f"is_metro FAIL: City='{city}', District='{district}' not in {metros}")
    return False

def is_special_state(location_dict):
    rules = get_zone_rules()
    state = location_dict["state"]
    return state in rules['special_states']


# --- 3. CSV/DB REGION LOGIC ---
# CSV_CACHE is removed as we query DB now

def get_csv_region_details(pincode: int, csv_filename: str = "BlueDart_Serviceable Pincodes.csv"):
    """
    Fetch serviceable details from ServiceablePincode model.
    Previously read from valid CSV files.
    """
    # Map filenames to Courier names or use a direct mapping?
    # Logic in load_couriers/import suggests:
    # "BlueDart_Serviceable Pincodes.csv" -> BlueDart
    # "ACPL..." -> ACPL? We need to know WHICH carrier this file belongs to.
    
    # Heuristic mapping based on usage
    carrier_name = None
    if "BlueDart" in csv_filename:
        carrier_name = "Blue Dart"
    # For ACPL, we might need a different approach or ensure ACPL data is in the same table.
    # If the user says "there is no acpl serviceable pincode list", then maybe we only care about BlueDart for now?
    # But `get_zone` logic for 'city_specific' uses a generic `csv_file` param.
    
    if not carrier_name:
        # Fallback: Can't query DB without knowing carrier.
        # But wait, ServiceablePincode is linked to Courier. 
        # The caller (get_zone) MIGHT know the carrier if we passed it in!
        # `get_zone` receives `carrier_config` dict. It doesn't receive the Courier object or ID directly usually.
        # However, `carrier_config` has "carrier_name" usually?
        # Let's check `get_rate_dict` in models.py -> it includes "carrier_name".
        pass

    # If we can't determine carrier, we might fail. 
    # But let's look at usage. 
    # 1. get_zone(..., "pincode_region_csv") -> passes "csv_file".
    # We should update `get_zone` to pass `carrier_name` to this function instead of `csv_file`.
    
    # REFACTOR: 
    # This function allows `csv_filename` backward compat but we prefer querying by Carrier Name if possible.
    # Since we can't easily change the signature everywhere safely without checking all deps, 
    # lets assume "BlueDart" is the primary user of `pincode_region_csv`.
    
    if carrier_name:
        try:
            sp = ServiceablePincode.objects.filter(courier__name__icontains=carrier_name, pincode=pincode).first()
            if sp:
                return {
                    "REGION": sp.region_code,
                    "Extended Delivery Location": "Y" if sp.is_edl else "N",
                    "EDL Distance": sp.edl_distance,
                    "Embargo": "Y" if sp.is_embargo else "N",
                    "CITY": sp.city_name, # Populated if available
                    # Add compatibility keys
                    "PINCODE": sp.pincode
                }
        except Exception as e:
            logger.error(f"Error fetching serviceable pincode {pincode} for {carrier_name}: {e}")
            
    return None

# --- 4. UNIFIED ZONE LOGIC (UPDATED) ---
def get_zone(source_pincode: int, dest_pincode: int, carrier_config: dict):
    """
    Determines the Zone Identifier based on Carrier Logic.
    Returns: (zone_id, description, logic_type)
    """
    s_loc = get_location_details(source_pincode)
    d_loc = get_location_details(dest_pincode)

    routing = carrier_config.get("routing_logic", {})
    logic_type = routing.get("type")
    
    # EXTRACT CARRIER NAME if available to help DB lookups
    # Prefer original_name (e.g. "ACPL Surface 50kg") over keys that might have aggregator prefixes
    carrier_name = carrier_config.get("original_name") or carrier_config.get("carrier_name", "")


    # --- LOGIC 4: CSV REGION (Blue Dart / Others) ---
    if logic_type == "pincode_region_csv":
         # Logic previously used 'csv_file' from config to load CSV.
         # Now we hope to use ServiceablePincode table.
         # If carrier_name is BlueDart, use DB.
         if "BlueDart" in carrier_name or "BlueDart" in routing.get("csv_file", ""):
             details = get_csv_region_details(dest_pincode, "BlueDart_Serviceable Pincodes.csv")
             
             if not details:
                  return None, "Pincode Not Found in Carrier DB", logic_type
             
             if details.get("Embargo") == "Y":
                  return None, "Embargo (Not Servicable)", logic_type

             return details.get("REGION"), f"Region: {details.get('REGION')}", logic_type
         
         # Fallback for unknown CSVs?
         return None, "Configuration Error: CSV migration pending for this carrier", logic_type


    if not s_loc or not d_loc:
        return None, "Invalid Pincode", None
    
    # --- LOGIC 1: CITY-TO-CITY via CSV (e.g., ACPL) ---
    if routing.get("is_city_specific"):
        # Validate against ServiceablePincode DB if carrier is known
        # ensuring we only support active ACPL locations.
        
        s_city_name = s_loc["original_city"]
        d_city_name = d_loc["original_city"]
        
        # Helper to fetch mapped city name from ServiceablePincode
        def get_acpl_city(pincode, default_city):
            if not carrier_name: return default_city
            try:
                # Carrier name match (e.g. "ACPL")
                sp = ServiceablePincode.objects.filter(
                    courier__name__icontains=carrier_name.split()[0], # Heuristic: First word "ACPL"
                    pincode=pincode
                ).first()
                return sp.city_name.lower() if (sp and sp.city_name) else None
            except Exception:
                return None

        # Try to resolve Mapped Cities (e.g. Thane -> Bhiwandi)
        # If DB record missing, assume NOT SERVICEABLE for ACPL (Stricter logic)
        mapped_s_city = get_acpl_city(source_pincode, s_city_name)
        mapped_d_city = get_acpl_city(dest_pincode, d_city_name)
        
        if not mapped_s_city or not mapped_d_city:
             return None, "Cities not identified in service list", "city_specific"

        hub_city = routing.get("hub_city", "bhiwandi").lower()
        
        source_is_hub = hub_city in mapped_s_city
        dest_is_hub = hub_city in mapped_d_city
        
        if source_is_hub or dest_is_hub:
            # Return the NON-HUB city as the zone identifier
            serviceable_city = mapped_d_city if source_is_hub else mapped_s_city
            return serviceable_city, f"City Route: {mapped_s_city} <-> {mapped_d_city}", "city_specific"
        
        return None, "Route not connected to Hub", "city_specific"

    # --- LOGIC 2: CARRIER SPECIFIC ZONE MATRIX ---
    zone_map = carrier_config.get("zone_mapping")
    if zone_map:
        def find_mapped_zone(loc_details, mapping):
            state = loc_details["state"]
            for key, code in mapping.items():
                if normalize_name(key, "state") == state:
                    return code
            return None

        origin_zone = find_mapped_zone(s_loc, zone_map)
        dest_zone = find_mapped_zone(d_loc, zone_map)

        if origin_zone and dest_zone:
            return (origin_zone, dest_zone), f"Matrix: {origin_zone}->{dest_zone}", "matrix"
            
        return "z_d", "Zone Mapping Failed (Defaulting)", "matrix"

    # --- LOGIC 3: STANDARD ZONAL ---
    if is_special_state(s_loc) or is_special_state(d_loc):
         return "z_f", "Zone E (North-East & J&K)", "standard"
    
    if is_metro(s_loc) and is_metro(d_loc):
        return "z_a", "Zone A (Metropolitan)", "standard"
        
    if s_loc["state"] == d_loc["state"]:
        return "z_b", "Zone B (Regional)", "standard"
        
    if s_loc["city"] != d_loc["city"]:
        return "z_c", "Zone C (Intercity)", "standard"
        
    return "z_d", "Zone D (Pan-India)", "standard"

# --- 5. LEGACY WRAPPER ---
def get_zone_column(source_pincode: int, dest_pincode: int):
    """
    Legacy wrapper for existing views.
    """
    dummy_config = {
        "routing_logic": {
            "is_city_specific": False
        },
        "carrier_name": "Legacy"
    }
    
    zone_id, desc, logic = get_zone(source_pincode, dest_pincode, dummy_config)
    return zone_id, desc


