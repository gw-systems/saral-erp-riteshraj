"""
Django signals for automatic cache invalidation.

Automatically invalidates rate card caches when Courier-related models change.
Eliminates the need for manual cache.delete() calls throughout the codebase.
"""
from contextlib import contextmanager
from threading import local

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache

from .constants import CacheKeys
from .logging_utils import log_cache_operation


# Import will happen when Django apps are ready, so we use string references
# to avoid circular imports

_cache_signal_state = local()


def _cache_invalidation_suppressed() -> bool:
    return getattr(_cache_signal_state, "suppress_count", 0) > 0


@contextmanager
def suppress_carrier_cache_invalidation():
    current = getattr(_cache_signal_state, "suppress_count", 0)
    _cache_signal_state.suppress_count = current + 1
    try:
        yield
    finally:
        _cache_signal_state.suppress_count = max(
            getattr(_cache_signal_state, "suppress_count", 1) - 1,
            0,
        )


@receiver([post_save, post_delete], sender='courier.Courier')
def invalidate_carrier_cache_on_courier_change(sender, instance, **kwargs):
    """
    Invalidate carrier rate card cache when Courier model changes.
    
    Triggered on:
    - Courier creation
    - Courier updates (save)
    - Courier deletion
    """
    if _cache_invalidation_suppressed():
        return

    signal = kwargs.get('signal')
    signal_name = signal.__name__ if hasattr(signal, '__name__') else str(signal)
    
    cache.delete(CacheKeys.CARRIER_RATE_CARDS)
    log_cache_operation(
        f"Invalidated carrier cache due to Courier change",
        carrier=instance.name,
        signal=signal_name
    )


@receiver([post_save, post_delete], sender='courier.CourierZoneRate')
def invalidate_carrier_cache_on_zone_rate_change(sender, instance, **kwargs):
    """
    Invalidate carrier rate card cache when CourierZoneRate changes.
    
    Triggered when zone rates are added, updated, or deleted.
    """
    if _cache_invalidation_suppressed():
        return

    cache.delete(CacheKeys.CARRIER_RATE_CARDS)
    log_cache_operation(
        f"Invalidated carrier cache due to CourierZoneRate change",
        courier=instance.courier.name,
        zone_code=instance.zone_code,
        rate_type=instance.rate_type
    )


@receiver([post_save, post_delete], sender='courier.CityRoute')
def invalidate_carrier_cache_on_city_route_change(sender, instance, **kwargs):
    """
    Invalidate carrier rate card cache when CityRoute changes.
    
    Triggered when city routes are added, updated, or deleted.
    """
    if _cache_invalidation_suppressed():
        return

    cache.delete(CacheKeys.CARRIER_RATE_CARDS)
    log_cache_operation(
        f"Invalidated carrier cache due to CityRoute change",
        courier=instance.courier.name,
        city=instance.city_name
    )


@receiver([post_save, post_delete], sender='courier.CustomZone')
def invalidate_carrier_cache_on_custom_zone_change(sender, instance, **kwargs):
    """
    Invalidate carrier rate card cache when CustomZone changes.
    
    Triggered when custom zones are added, updated, or deleted.
    """
    if _cache_invalidation_suppressed():
        return

    cache.delete(CacheKeys.CARRIER_RATE_CARDS)
    log_cache_operation(
        f"Invalidated carrier cache due to CustomZone change",
        courier=instance.courier.name,
        location=instance.location_name,
        zone_code=instance.zone_code
    )


@receiver([post_save, post_delete], sender='courier.CustomZoneRate')
def invalidate_carrier_cache_on_custom_zone_rate_change(sender, instance, **kwargs):
    """
    Invalidate carrier rate card cache when CustomZoneRate changes.
    
    Triggered when custom zone rates are added, updated, or deleted.
    """
    if _cache_invalidation_suppressed():
        return

    cache.delete(CacheKeys.CARRIER_RATE_CARDS)
    log_cache_operation(
        f"Invalidated carrier cache due to CustomZoneRate change",
        courier=instance.courier.name,
        from_zone=instance.from_zone,
        to_zone=instance.to_zone
    )


@receiver([post_save, post_delete], sender='courier.DeliverySlab')
def invalidate_carrier_cache_on_delivery_slab_change(sender, instance, **kwargs):
    """
    Invalidate carrier rate card cache when DeliverySlab changes.
    
    Triggered when delivery slabs are added, updated, or deleted.
    """
    if _cache_invalidation_suppressed():
        return

    cache.delete(CacheKeys.CARRIER_RATE_CARDS)
    log_cache_operation(
        f"Invalidated carrier cache due to DeliverySlab change",
        courier=instance.courier.name,
        min_weight=instance.min_weight,
        max_weight=instance.max_weight
    )


# Utility function for manual cache invalidation if needed
def invalidate_all_carrier_caches():
    """
    Manually invalidate all carrier-related caches.
    
    Use sparingly - signals should handle most cases automatically.
    """
    cache.delete(CacheKeys.CARRIER_RATE_CARDS)
    cache.delete(CacheKeys.FTL_RATE_CARDS)
    log_cache_operation("Manually invalidated all carrier caches")
