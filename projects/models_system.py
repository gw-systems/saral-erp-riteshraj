from django.db import models


class SystemSettings(models.Model):
    setting_key = models.CharField(max_length=50, primary_key=True)
    setting_value = models.CharField(max_length=100)
    setting_description = models.TextField(blank=True)
    setting_updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'system_settings'
        verbose_name = 'System Setting'
        verbose_name_plural = 'System Settings'

    def __str__(self):
        return f"{self.setting_key}: {self.setting_value}"