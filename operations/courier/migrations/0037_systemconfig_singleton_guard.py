from django.db import migrations, models


def normalize_system_config(apps, schema_editor):
    SystemConfig = apps.get_model("courier", "SystemConfig")
    configs = list(SystemConfig.objects.order_by("id"))
    if not configs:
        return

    field_names = [f.name for f in SystemConfig._meta.fields if f.name != "id"]
    if not SystemConfig.objects.filter(pk=1).exists():
        source = configs[0]
        payload = {name: getattr(source, name) for name in field_names}
        SystemConfig.objects.create(pk=1, **payload)

    SystemConfig.objects.exclude(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("courier", "0036_rename_orders_external_order_id_idx_orders_externa_1cd7d5_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(normalize_system_config, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="systemconfig",
            constraint=models.CheckConstraint(
                condition=models.Q(pk=1),
                name="system_config_singleton_pk_1",
            ),
        ),
    ]
