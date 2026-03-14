from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class TransportSheetConfig(models.Model):
    """
    Singleton config for the manual transport Google Sheet.
    The actual GoogleSheetsToken is connected via the existing OAuth flow
    in expense_log (user connects sheet from the frontend).
    """
    token_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="ID of the GoogleSheetsToken to use for syncing (set after connecting sheet via OAuth)"
    )
    is_active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_rows = models.IntegerField(default=0, help_text="Rows processed in last sync")
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transport_sheet_config_updates'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Transport Sheet Config'

    def __str__(self):
        return f"Transport Sheet Config (token_id={self.token_id})"

    @classmethod
    def load(cls):
        """Load singleton config"""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
