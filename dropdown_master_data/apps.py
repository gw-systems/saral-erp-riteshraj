from django.apps import AppConfig


class DropdownMasterDataConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dropdown_master_data'
    
    def ready(self):
        """Import signals when app is ready"""
        import dropdown_master_data.signals