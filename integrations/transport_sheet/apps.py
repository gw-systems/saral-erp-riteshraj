from django.apps import AppConfig


class TransportSheetConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'integrations.transport_sheet'
    verbose_name = 'Transport Sheet Sync'
