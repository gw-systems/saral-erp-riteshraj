"""
Gmail Leads App Configuration
"""

from django.apps import AppConfig


class GmailLeadsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'integrations.gmail_leads'
    verbose_name = 'Gmail Lead Fetcher'
