"""
Callyzer App Configuration
"""

from django.apps import AppConfig


class CallyzerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'integrations.callyzer'
    verbose_name = 'Callyzer Integration'

    def ready(self):
        """Import signals if needed"""
        pass
