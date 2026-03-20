from decimal import Decimal

from django.db import migrations, models
from django.utils.text import slugify


def _normalize_text(value, fallback):
    normalized = slugify(str(value or "").strip())
    return normalized or fallback


def _normalize_weight(value):
    try:
        decimal_value = Decimal(str(value))
    except Exception:
        decimal_value = Decimal("0.5")

    normalized = format(decimal_value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized.replace("-", "neg").replace(".", "p") or "0"


def _build_code(aggregator, display_name, service_category, carrier_mode, min_weight):
    return "-".join(
        [
            _normalize_text(aggregator, "generic"),
            _normalize_text(display_name, "courier"),
            _normalize_text(service_category, "surface"),
            _normalize_text(carrier_mode, "surface"),
            _normalize_weight(min_weight),
        ]
    )


def populate_courier_codes(apps, schema_editor):
    Courier = apps.get_model("courier", "Courier")
    ServiceConstraints = apps.get_model("courier", "ServiceConstraints")

    seen_codes = {}

    for courier in Courier.objects.all().order_by("id"):
        min_weight = (
            ServiceConstraints.objects.filter(courier_link_id=courier.id)
            .values_list("min_weight", flat=True)
            .first()
        )
        code = _build_code(
            aggregator=getattr(courier, "aggregator", ""),
            display_name=getattr(courier, "display_name", "") or getattr(courier, "name", ""),
            service_category=getattr(courier, "service_category", ""),
            carrier_mode=getattr(courier, "carrier_mode", ""),
            min_weight=min_weight if min_weight is not None else 0.5,
        )

        existing_id = seen_codes.get(code)
        if existing_id and existing_id != courier.id:
            raise RuntimeError(
                f"Duplicate courier_code '{code}' generated for courier IDs {existing_id} and {courier.id}. "
                "Resolve duplicate courier identities before applying this migration."
            )

        seen_codes[code] = courier.id
        Courier.objects.filter(pk=courier.pk).update(courier_code=code)


class Migration(migrations.Migration):

    dependencies = [
        ("courier", "0037_systemconfig_singleton_guard"),
    ]

    operations = [
        migrations.AddField(
            model_name="courier",
            name="courier_code",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Stable immutable courier identity used for ERP/bootstrap integration. "
                    "Derived from aggregator, display name, service category, carrier mode, and min weight."
                ),
                max_length=255,
                null=True,
            ),
        ),
        migrations.RunPython(populate_courier_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="courier",
            name="courier_code",
            field=models.CharField(
                editable=False,
                help_text=(
                    "Stable immutable courier identity used for ERP/bootstrap integration. "
                    "Derived from aggregator, display name, service category, carrier mode, and min weight."
                ),
                max_length=255,
                unique=True,
            ),
        ),
    ]
