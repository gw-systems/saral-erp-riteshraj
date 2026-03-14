"""
Google Ads Integration App Configuration
"""

from django.apps import AppConfig


class GoogleAdsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'integrations.google_ads'
    verbose_name = 'Google Ads Integration'
