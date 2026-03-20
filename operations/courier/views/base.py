"""
Base utilities and shared imports for views.
Contains shared functions and configuration.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, action, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from django.utils import timezone
from django.core.cache import cache
import logging
import secrets

from ..serializers import (
    OrderSerializer, OrderUpdateSerializer, RateRequestSerializer,
    CarrierSelectionSerializer, NewCarrierSerializer, FTLOrderSerializer,
    FTLRateRequestSerializer
)
from ..engine import calculate_cost
from ..models import Order, OrderStatus, PaymentMode, FTLOrder, Courier, SystemConfig
from ..permissions import IsAdminToken
from ..zones import get_zone_column


logger = logging.getLogger('courier')


def load_rates():
    """
    Load rate cards with caching for performance.
    Cache timeout: 5 minutes (300 seconds).
    """
    CACHE_KEY = 'carrier_rate_cards'
    CACHE_TIMEOUT = 300  # 5 minutes
    
    # Try to get from cache first
    rates = cache.get(CACHE_KEY)
    if rates is not None:
        return rates
    
    # Cache miss - load from DB
    try:
        couriers = (
            Courier.objects
            .filter(is_active=True)
            .select_related("fees_config", "constraints_config", "fuel_config_obj", "routing_config")
            .prefetch_related("zone_rates")
        )
        rates = [c.get_rate_dict() for c in couriers]
        
        if not rates:
            logger.warning("No active couriers found in database")
            
        # Store in cache
        cache.set(CACHE_KEY, rates, CACHE_TIMEOUT)
        logger.info(f"Rate cards loaded from DB and cached ({len(rates)} carriers)")
        return rates

    except Exception as e:
        logger.error(f"Unexpected error loading rate cards from DB: {e}")
        return []


from ..models import FTLRate

def load_ftl_rates():
    """
    Load FTL rates from DB with caching.
    Cache timeout: 5 minutes (300 seconds).
    Returns nested dict: {Source: {Dest: {Type: Rate}}}
    """
    CACHE_KEY = 'ftl_rate_cards'
    CACHE_TIMEOUT = 300  # 5 minutes
    
    # Try to get from cache first
    rates = cache.get(CACHE_KEY)
    if rates is not None:
        return rates
    
    # Cache miss - load from DB
    try:
        rates = {}
        qs = FTLRate.objects.all()
        
        for obj in qs:
            source = obj.source_city
            dest = obj.destination_city
            
            if source not in rates:
                rates[source] = {}
            if dest not in rates[source]:
                rates[source][dest] = {}
                
            # Store as float/int for compatibility with existing view logic
            rates[source][dest][obj.truck_type] = float(obj.rate)
        
        # Store in cache
        cache.set(CACHE_KEY, rates, CACHE_TIMEOUT)
        logger.info(f"FTL rates loaded from DB ({qs.count()} records)")
        return rates
        
    except Exception as e:
        logger.error(f"Error loading FTL rates from DB: {e}")
        return {}


def invalidate_rates_cache():
    """
    Invalidate all rate-related caches.
    Call this after updating rate cards via admin endpoints.
    """
    cache.delete('carrier_rate_cards')
    cache.delete('ftl_rate_cards')
    logger.info("Rate card caches invalidated")


def _generate_unique_number(prefix: str, model):
    """
    Generate a collision-resistant order number.
    Uses timestamp + randomness to avoid concurrent insert races.
    """
    for _ in range(10):
        now_part = timezone.now().strftime("%Y%m%d%H%M%S%f")
        token_part = secrets.token_hex(2)
        number = f"{prefix}{now_part}-{token_part}"
        if not model.objects.filter(order_number=number).exists():
            return number
    raise RuntimeError(f"Unable to generate unique order number for prefix '{prefix}'.")


def generate_order_number():
    """Generate unique order number."""
    return _generate_unique_number("ORD-", Order)


def generate_ftl_order_number():
    """Generate unique FTL order number."""
    return _generate_unique_number("FTL-", FTLOrder)


def calculate_ftl_price(base_price):
    """Calculate FTL price with escalation and GST
    Formula: base_price + escalation, then add GST
    Uses rates from global settings.
    """
    conf = SystemConfig.get_solo()
    ESCALATION_RATE = float(conf.escalation_rate)
    GST_RATE = float(conf.gst_rate)
    
    escalation_amount = base_price * ESCALATION_RATE
    price_with_escalation = base_price + escalation_amount
    gst_amount = price_with_escalation * GST_RATE
    total_price = price_with_escalation + gst_amount
    
    return {
        "base_price": round(base_price, 2),
        "escalation_amount": round(escalation_amount, 2),
        "price_with_escalation": round(price_with_escalation, 2),
        "gst_amount": round(gst_amount, 2),
        "total_price": round(total_price, 2)
    }
