"""
Constants module for the courier application.

Centralizes all hardcoded strings to prevent typos and provide IDE autocomplete.
Single source of truth for carrier names, hub cities, file names, and cache keys.
"""


class CarrierNames:
    """Standard carrier name constants."""
    
    # Courier Carriers
    BLUEDART = "Blue Dart"
    EKART_SURFACE = "Ekart Surface"
    EKART_AIR = "Ekart Air"
    DELHIVERY_SURFACE = "Delhivery Surface"
    DELHIVERY_AIR = "Delhivery Air"
    ACPL_SURFACE_50KG = "ACPL Surface 50kg"
    VTRANS_100KG = "V-Trans 100kg"
    
    # Add more carriers as needed
    @classmethod
    def all(cls):
        """Return all carrier names."""
        return [
            value for name, value in vars(cls).items()
            if not name.startswith('_') and isinstance(value, str)
        ]


class HubCities:
    """Hub city name constants."""
    
    BHIWANDI = "bhiwandi"
    MUMBAI = "mumbai"
    DELHI = "delhi"
    BANGALORE = "bangalore"
    CHENNAI = "chennai"
    KOLKATA = "kolkata"
    HYDERABAD = "hyderabad"
    PUNE = "pune"


class CSVFiles:
    """CSV filename constants for serviceable pincodes."""
    
    BLUEDART_SERVICEABLE = "BlueDart_Serviceable Pincodes.csv"
    ACPL_SERVICEABLE = "ACPL_Serviceable_Pincodes.csv"
    
    # Add more CSV files as needed


class CacheKeys:
    """Cache key constants for Django cache."""
    
    CARRIER_RATE_CARDS = "carrier_rate_cards"
    FTL_RATE_CARDS = "ftl_rate_cards"
    PINCODE_MASTER = "pincode_master"
    PINCODE_LOOKUP = "pincode_{}"  # Format with pincode number
    
    @staticmethod
    def pincode_lookup(pincode: int) -> str:
        """Generate cache key for specific pincode."""
        return f"pincode_{pincode}"


class RateLogicTypes:
    """Rate logic type constants matching Courier model choices."""
    
    ZONAL_STANDARD = "Zonal_Standard"
    ZONAL_CUSTOM = "Zonal_Custom"
    CITY_TO_CITY = "City_To_City"
    REGION_CSV = "Region_CSV"


class CarrierTypes:
    """Carrier type constants."""
    
    COURIER = "Courier"
    PTL = "PTL"
    FTL = "FTL"


class CarrierModes:
    """Carrier mode constants."""
    
    SURFACE = "Surface"
    AIR = "Air"


class ZoneCodes:
    """Standard zone code constants."""
    
    # Standard alphanumeric zones
    ZONE_A = "z_a"
    ZONE_B = "z_b"
    ZONE_C = "z_c"
    ZONE_D = "z_d"
    ZONE_E = "z_e"
    ZONE_F = "z_f"
    
    # Named zones
    LOCAL = "local"
    METRO = "metro"
    REGIONAL = "regional"
    NATIONAL = "national"
    SPECIAL = "special"
