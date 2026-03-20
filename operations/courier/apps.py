from django.apps import AppConfig


class CourierConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "operations.courier"
    label = "courier"
    verbose_name = "Operations Courier"

    def ready(self):
        """
        Register signal handlers when Django starts.

        Imports signals module to connect automatic cache invalidation
        handlers to Courier model changes.
        """
        from . import signals  # noqa: F401 - Import registers signal handlers
