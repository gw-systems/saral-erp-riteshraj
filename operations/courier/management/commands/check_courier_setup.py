from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from ...models import (
    CityRoute,
    Courier,
    CourierZoneRate,
    CustomZone,
    CustomZoneRate,
    DeliverySlab,
    FTLRate,
    LocationAlias,
    Pincode,
    ServiceablePincode,
    SystemConfig,
    Warehouse,
    ZoneRule,
)
from ...models_refactored import FeeStructure, FuelConfiguration, RoutingLogic, ServiceConstraints
from ...snapshot_utils import FILE_NAMES, SNAPSHOT_VERSION, default_snapshot_dir, file_sha256, read_json


class Command(BaseCommand):
    help = "Verify courier snapshot integrity and local courier setup readiness."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input-dir",
            dest="input_dir",
            help="Directory containing a courier snapshot package.",
        )

    def handle(self, *args, **options):
        input_dir = Path(options.get("input_dir") or default_snapshot_dir(settings.BASE_DIR))
        manifest_path = input_dir / FILE_NAMES["manifest"]
        if not manifest_path.exists():
            raise CommandError(f"Snapshot manifest not found: {manifest_path}")

        manifest = read_json(manifest_path)
        if manifest.get("snapshot_version") != SNAPSHOT_VERSION:
            raise CommandError(
                f"Unsupported snapshot version {manifest.get('snapshot_version')}. "
                f"Expected {SNAPSHOT_VERSION}."
            )

        snapshot_couriers = read_json(input_dir / FILE_NAMES["couriers"])
        snapshot_codes = {row["courier_code"] for row in snapshot_couriers}
        local_codes = set(
            Courier.objects.exclude(courier_code__isnull=True)
            .exclude(courier_code="")
            .values_list("courier_code", flat=True)
        )

        errors = []
        warnings = []

        for filename, meta in (manifest.get("files") or {}).items():
            path = input_dir / filename
            if not path.exists():
                errors.append(f"Missing snapshot file: {path}")
                continue
            actual_sha = file_sha256(path)
            if meta.get("sha256") and meta["sha256"] != actual_sha:
                errors.append(f"Checksum mismatch for {filename}")

        duplicate_codes = (
            Courier.objects.values("courier_code")
            .exclude(courier_code__isnull=True)
            .exclude(courier_code="")
            .annotate(code_count=Count("id"))
            .filter(code_count__gt=1)
        )
        if duplicate_codes.exists():
            errors.append("Duplicate courier_code values detected in local DB.")

        missing_codes = sorted(snapshot_codes - local_codes)
        extra_codes = sorted(local_codes - snapshot_codes)
        if missing_codes:
            errors.append(f"Missing snapshot courier codes: {', '.join(missing_codes[:10])}")
        if extra_codes:
            warnings.append(f"Extra local courier codes not present in snapshot: {', '.join(extra_codes[:10])}")

        snapshot_filter = {"courier_link__courier_code__in": snapshot_codes}
        courier_filter = {"courier__courier_code__in": snapshot_codes}

        self._compare_count(
            manifest,
            "couriers",
            Courier.objects.filter(courier_code__in=snapshot_codes).count(),
            errors,
        )
        self._compare_count(
            manifest,
            "fee_structures",
            FeeStructure.objects.filter(**snapshot_filter).count(),
            errors,
        )
        self._compare_count(
            manifest,
            "service_constraints",
            ServiceConstraints.objects.filter(**snapshot_filter).count(),
            errors,
        )
        self._compare_count(
            manifest,
            "fuel_configurations",
            FuelConfiguration.objects.filter(**snapshot_filter).count(),
            errors,
        )
        self._compare_count(
            manifest,
            "routing_logics",
            RoutingLogic.objects.filter(**snapshot_filter).count(),
            errors,
        )
        self._compare_count(
            manifest,
            "courier_zone_rates",
            CourierZoneRate.objects.filter(**courier_filter).count(),
            errors,
        )
        self._compare_count(
            manifest,
            "city_routes",
            CityRoute.objects.filter(**courier_filter).count(),
            errors,
        )
        self._compare_count(
            manifest,
            "delivery_slabs",
            DeliverySlab.objects.filter(**courier_filter).count(),
            errors,
        )
        self._compare_count(
            manifest,
            "custom_zones",
            CustomZone.objects.filter(**courier_filter).count(),
            errors,
        )
        self._compare_count(
            manifest,
            "custom_zone_rates",
            CustomZoneRate.objects.filter(**courier_filter).count(),
            errors,
        )
        self._compare_count(manifest, "pincodes", Pincode.objects.count(), errors)
        self._compare_count(
            manifest,
            "serviceable_pincodes",
            ServiceablePincode.objects.filter(**courier_filter).count(),
            errors,
        )
        self._compare_count(manifest, "ftl_rates", FTLRate.objects.count(), errors)
        self._compare_count(manifest, "zone_rules", ZoneRule.objects.count(), errors)
        self._compare_count(manifest, "location_aliases", LocationAlias.objects.count(), errors)
        self._compare_count(manifest, "system_config", SystemConfig.objects.count(), errors)
        self._compare_optional_count(
            manifest,
            "courier_warehouses",
            Warehouse.objects.count(),
            warnings,
        )

        if FeeStructure.objects.filter(**snapshot_filter).count() != len(snapshot_codes):
            errors.append("Not every snapshot courier has exactly one fee structure.")
        if ServiceConstraints.objects.filter(**snapshot_filter).count() != len(snapshot_codes):
            errors.append("Not every snapshot courier has exactly one service constraint.")
        if FuelConfiguration.objects.filter(**snapshot_filter).count() != len(snapshot_codes):
            errors.append("Not every snapshot courier has exactly one fuel configuration.")
        if RoutingLogic.objects.filter(**snapshot_filter).count() != len(snapshot_codes):
            errors.append("Not every snapshot courier has exactly one routing configuration.")
        if SystemConfig.objects.count() > 1:
            errors.append("SystemConfig singleton violated: more than one row exists.")

        self.stdout.write("Courier setup verification summary:")
        self.stdout.write(f"  - snapshot version: {manifest['snapshot_version']}")
        self.stdout.write(f"  - snapshot couriers: {len(snapshot_codes)}")
        self.stdout.write(f"  - local populated courier codes: {len(local_codes)}")

        for warning in warnings:
            self.stdout.write(self.style.WARNING(f"WARNING: {warning}"))

        if errors:
            for error in errors:
                self.stdout.write(self.style.ERROR(f"ERROR: {error}"))
            raise CommandError("Courier setup verification failed.")

        self.stdout.write(self.style.SUCCESS("Courier setup verification passed."))

    def _compare_count(self, manifest, dataset_key, actual_count, errors):
        expected_count = (manifest.get("counts") or {}).get(dataset_key)
        if expected_count is None:
            errors.append(f"Manifest missing count for dataset '{dataset_key}'.")
            return
        if int(expected_count) != int(actual_count):
            errors.append(
                f"Count mismatch for '{dataset_key}': expected {expected_count}, got {actual_count}."
            )

    def _compare_optional_count(self, manifest, dataset_key, actual_count, warnings):
        expected_count = (manifest.get("counts") or {}).get(dataset_key)
        if expected_count is None:
            return
        if int(expected_count) != int(actual_count):
            warnings.append(
                f"Count mismatch for optional dataset '{dataset_key}': expected {expected_count}, got {actual_count}."
            )
