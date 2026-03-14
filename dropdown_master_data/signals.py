"""
Signals for Dropdown Master Data
Handles automatic sync between StorageUnit and BillingUnit.
"""

from django.db.models.signals import post_save, post_delete, pre_delete
from django.dispatch import receiver
from .models import StorageUnit, BillingUnit
from .services import clear_dropdown_cache


# Flag to prevent infinite loop during sync
_syncing = False


@receiver(post_save, sender=StorageUnit)
def sync_storage_to_billing(sender, instance, created, **kwargs):
    """
    When StorageUnit is created/updated, sync to BillingUnit.
    """
    global _syncing
    
    if _syncing:
        return
    
    try:
        _syncing = True
        
        # Create or update corresponding BillingUnit
        BillingUnit.objects.update_or_create(
            code=instance.code,
            defaults={
                'label': instance.label,
                'is_active': instance.is_active,
                'display_order': instance.display_order,
                'updated_by': instance.updated_by,
            }
        )
        
        # Clear cache for both
        clear_dropdown_cache('StorageUnit')
        clear_dropdown_cache('BillingUnit')
        
    finally:
        _syncing = False


@receiver(post_save, sender=BillingUnit)
def sync_billing_to_storage(sender, instance, created, **kwargs):
    """
    When BillingUnit is created/updated, sync to StorageUnit.
    """
    global _syncing
    
    if _syncing:
        return
    
    try:
        _syncing = True
        
        # Create or update corresponding StorageUnit
        StorageUnit.objects.update_or_create(
            code=instance.code,
            defaults={
                'label': instance.label,
                'is_active': instance.is_active,
                'display_order': instance.display_order,
                'updated_by': instance.updated_by,
            }
        )
        
        # Clear cache for both
        clear_dropdown_cache('StorageUnit')
        clear_dropdown_cache('BillingUnit')
        
    finally:
        _syncing = False


@receiver(pre_delete, sender=StorageUnit)
def sync_storage_delete(sender, instance, **kwargs):
    """
    When StorageUnit is deleted, soft-delete corresponding BillingUnit.
    Note: We use soft delete (is_active=False) instead of hard delete.
    """
    global _syncing
    
    if _syncing:
        return
    
    try:
        _syncing = True
        
        # Soft delete the corresponding BillingUnit
        try:
            billing_unit = BillingUnit.objects.get(code=instance.code)
            billing_unit.is_active = False
            billing_unit.save()
        except BillingUnit.DoesNotExist:
            pass
        
        # Clear cache for both
        clear_dropdown_cache('StorageUnit')
        clear_dropdown_cache('BillingUnit')
        
    finally:
        _syncing = False


@receiver(pre_delete, sender=BillingUnit)
def sync_billing_delete(sender, instance, **kwargs):
    """
    When BillingUnit is deleted, soft-delete corresponding StorageUnit.
    Note: We use soft delete (is_active=False) instead of hard delete.
    """
    global _syncing
    
    if _syncing:
        return
    
    try:
        _syncing = True
        
        # Soft delete the corresponding StorageUnit
        try:
            storage_unit = StorageUnit.objects.get(code=instance.code)
            storage_unit.is_active = False
            storage_unit.save()
        except StorageUnit.DoesNotExist:
            pass
        
        # Clear cache for both
        clear_dropdown_cache('StorageUnit')
        clear_dropdown_cache('BillingUnit')
        
    finally:
        _syncing = False