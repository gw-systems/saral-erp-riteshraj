from django.apps import AppConfig


class ApolloConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'integrations.apollo'
    label = 'apollo'
    verbose_name = 'Apollo Integration'
