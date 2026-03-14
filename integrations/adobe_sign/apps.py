"""
Adobe Sign App Configuration
"""

from django.apps import AppConfig


class AdobeSignConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'integrations.adobe_sign'
    verbose_name = 'Adobe Sign E-Signature'

    def ready(self):
        """
        Import signal handlers when app is ready
        """
        pass
