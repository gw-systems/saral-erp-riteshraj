from decimal import Decimal
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_datetime

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
from ...signals import suppress_carrier_cache_invalidation, invalidate_all_carrier_caches
from ...snapshot_utils import (
    FILE_NAMES,
    SNAPSHOT_VERSION,
    default_snapshot_dir,
    file_sha256,
    iter_in_chunks,
    read_json,
    read_jsonl,
    read_jsonl_gz,
)


class Command(BaseCommand):
    help = "Bootstrap courier master/reference data from an exported snapshot package."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input-dir",
            dest="input_dir",
            help="Directory containing a courier snapshot package.",
        )

    def handle(self, *args, **options):
        input_dir = default_snapshot_dir(settings.BASE_DIR)
        if options.get("input_dir"):
            input_dir = options["input_dir"]
        input_dir = input_dir if hasattr(input_dir, "exists") else input_dir

        manifest_path = default_snapshot_dir(settings.BASE_DIR) / FILE_NAMES["manifest"]
        if options.get("input_dir"):
            from pathlib import Path

            input_dir = Path(options["input_dir"])
            manifest_path = input_dir / FILE_NAMES["manifest"]
        else:
            input_dir = default_snapshot_dir(settings.BASE_DIR)
            manifest_path = input_dir / FILE_NAMES["manifest"]

        if not manifest_path.exists():
            raise CommandError(f"Snapshot manifest not found: {manifest_path}")

        manifest = read_json(manifest_path)
        if manifest.get("snapshot_version") != SNAPSHOT_VERSION:
            raise CommandError(
                f"Unsupported snapshot version {manifest.get('snapshot_version')}. "
                f"Expected {SNAPSHOT_VERSION}."
            )

        self._verify_checksums(input_dir, manifest)

        couriers_payload = read_json(input_dir / FILE_NAMES["couriers"])
        fee_payload = read_json(input_dir / FILE_NAMES["fee_structures"])
        constraints_payload = read_json(input_dir / FILE_NAMES["service_constraints"])
        fuel_payload = read_json(input_dir / FILE_NAMES["fuel_configurations"])
        routing_payload = read_json(input_dir / FILE_NAMES["routing_logics"])
        city_routes_payload = read_json(input_dir / FILE_NAMES["city_routes"])
        delivery_slabs_payload = read_json(input_dir / FILE_NAMES["delivery_slabs"])
        custom_zones_payload = read_json(input_dir / FILE_NAMES["custom_zones"])
        custom_zone_rates_payload = read_json(input_dir / FILE_NAMES["custom_zone_rates"])
        ftl_rates_payload = read_json(input_dir / FILE_NAMES["ftl_rates"])
        zone_rules_payload = read_json(input_dir / FILE_NAMES["zone_rules"])
        location_aliases_payload = read_json(input_dir / FILE_NAMES["location_aliases"])
        system_config_payload = read_json(input_dir / FILE_NAMES["system_config"])
        warehouses_payload = self._read_optional_payload(
            input_dir / FILE_NAMES["courier_warehouses"]
        )

        with suppress_carrier_cache_invalidation():
            with transaction.atomic():
                courier_map = self._upsert_couriers(couriers_payload)
                snapshot_codes = set(courier_map.keys())
                snapshot_ids = [courier.id for courier in courier_map.values()]

                self._upsert_fee_structures(fee_payload, courier_map)
                self._upsert_service_constraints(constraints_payload, courier_map)
                self._upsert_fuel_configurations(fuel_payload, courier_map)
                self._upsert_routing_logics(routing_payload, courier_map)

                self._replace_zone_rates(input_dir, courier_map, snapshot_ids)
                self._replace_city_routes(city_routes_payload, courier_map, snapshot_ids)
                self._replace_delivery_slabs(delivery_slabs_payload, courier_map, snapshot_ids)
                self._replace_custom_zones(custom_zones_payload, courier_map, snapshot_ids)
                self._replace_custom_zone_rates(custom_zone_rates_payload, courier_map, snapshot_ids)

                self._replace_pincodes(input_dir)
                self._replace_serviceable_pincodes(input_dir, courier_map, snapshot_ids)
                self._replace_ftl_rates(ftl_rates_payload)
                self._replace_zone_rules(zone_rules_payload)
                self._replace_location_aliases(location_aliases_payload)
                self._replace_system_config(system_config_payload)
                self._upsert_warehouses(warehouses_payload)

        invalidate_all_carrier_caches()

        self.stdout.write(
            self.style.SUCCESS(
                f"Courier bootstrap completed successfully for {len(snapshot_codes)} courier codes."
            )
        )

    def _verify_checksums(self, input_dir, manifest):
        files = manifest.get("files") or {}
        for filename, meta in files.items():
            path = input_dir / filename
            if not path.exists():
                raise CommandError(f"Snapshot file missing: {path}")
            actual = file_sha256(path)
            expected = meta.get("sha256")
            if expected and actual != expected:
                raise CommandError(f"Checksum mismatch for {filename}")

    def _read_optional_payload(self, path):
        if not path.exists():
            return None
        try:
            return read_json(path)
        except UnicodeDecodeError:
            return json.loads(path.read_text(encoding="utf-16"))

    def _upsert_couriers(self, rows):
        courier_map = {}
        for row in rows:
            courier_code = row["courier_code"]
            defaults = {
                "name": row["name"],
                "display_name": row["display_name"],
                "aggregator": row["aggregator"],
                "carrier_type": row["carrier_type"],
                "carrier_mode": row["carrier_mode"],
                "service_category": row["service_category"],
                "is_active": row["is_active"],
                "shipdaak_courier_id": row["shipdaak_courier_id"],
                "legacy_rate_card_backup": row.get("legacy_rate_card_backup") or {},
            }
            try:
                courier, _ = Courier.objects.update_or_create(
                    courier_code=courier_code,
                    defaults=defaults,
                )
            except IntegrityError as exc:
                raise CommandError(
                    f"Failed to upsert courier '{courier_code}'. "
                    "This usually means a conflicting unique courier name already exists."
                ) from exc
            courier_map[courier_code] = courier
        self.stdout.write(f"  - couriers upserted: {len(courier_map)}")
        return courier_map

    def _upsert_fee_structures(self, rows, courier_map):
        for row in rows:
            courier = self._resolve_courier(row["courier_code"], courier_map)
            FeeStructure.objects.update_or_create(
                courier_link=courier,
                defaults={
                    "docket_fee": Decimal(str(row["docket_fee"])),
                    "eway_bill_fee": Decimal(str(row["eway_bill_fee"])),
                    "appointment_delivery_fee": Decimal(str(row["appointment_delivery_fee"])),
                    "cod_fixed": Decimal(str(row["cod_fixed"])),
                    "cod_percent": Decimal(str(row["cod_percent"])),
                    "hamali_per_kg": Decimal(str(row["hamali_per_kg"])),
                    "min_hamali": Decimal(str(row["min_hamali"])),
                    "fov_min": Decimal(str(row["fov_min"])),
                    "fov_insured_percent": Decimal(str(row["fov_insured_percent"])),
                    "fov_uninsured_percent": Decimal(str(row["fov_uninsured_percent"])),
                    "damage_claim_percent": Decimal(str(row["damage_claim_percent"])),
                    "other_charges": Decimal(str(row["other_charges"])),
                },
            )
        self.stdout.write(f"  - fee structures synced: {len(rows)}")

    def _upsert_service_constraints(self, rows, courier_map):
        for row in rows:
            courier = self._resolve_courier(row["courier_code"], courier_map)
            ServiceConstraints.objects.update_or_create(
                courier_link=courier,
                defaults={
                    "min_weight": float(row["min_weight"]),
                    "max_weight": float(row["max_weight"]),
                    "volumetric_divisor": int(row["volumetric_divisor"]),
                    "required_source_city": row.get("required_source_city"),
                },
            )
        self.stdout.write(f"  - service constraints synced: {len(rows)}")

    def _upsert_fuel_configurations(self, rows, courier_map):
        for row in rows:
            courier = self._resolve_courier(row["courier_code"], courier_map)
            FuelConfiguration.objects.update_or_create(
                courier_link=courier,
                defaults={
                    "is_dynamic": bool(row["is_dynamic"]),
                    "base_price": Decimal(str(row["base_price"])),
                    "ratio": Decimal(str(row["ratio"])),
                    "surcharge_percent": Decimal(str(row["surcharge_percent"])),
                },
            )
        self.stdout.write(f"  - fuel configurations synced: {len(rows)}")

    def _upsert_routing_logics(self, rows, courier_map):
        for row in rows:
            courier = self._resolve_courier(row["courier_code"], courier_map)
            RoutingLogic.objects.update_or_create(
                courier_link=courier,
                defaults={
                    "logic_type": row["logic_type"],
                    "serviceable_pincode_csv": row.get("serviceable_pincode_csv"),
                    "hub_city": row.get("hub_city"),
                    "hub_pincode_prefixes": row.get("hub_pincode_prefixes"),
                },
            )
        self.stdout.write(f"  - routing logics synced: {len(rows)}")

    def _replace_zone_rates(self, input_dir, courier_map, snapshot_ids):
        CourierZoneRate.objects.filter(courier_id__in=snapshot_ids).delete()
        rows = []
        for row in read_jsonl(input_dir / FILE_NAMES["courier_zone_rates"]):
            courier = self._resolve_courier(row["courier_code"], courier_map)
            rows.append(
                CourierZoneRate(
                    courier=courier,
                    zone_code=row["zone_code"],
                    rate_type=row["rate_type"],
                    rate=Decimal(str(row["rate"])),
                )
            )
        for batch in iter_in_chunks(rows, 1000):
            CourierZoneRate.objects.bulk_create(batch, batch_size=1000)
        self.stdout.write(f"  - courier zone rates replaced: {len(rows)}")

    def _replace_city_routes(self, rows, courier_map, snapshot_ids):
        CityRoute.objects.filter(courier_id__in=snapshot_ids).delete()
        payload = [
            CityRoute(
                courier=self._resolve_courier(row["courier_code"], courier_map),
                city_name=row["city_name"],
                rate_per_kg=Decimal(str(row["rate_per_kg"])),
            )
            for row in rows
        ]
        for batch in iter_in_chunks(payload, 1000):
            CityRoute.objects.bulk_create(batch, batch_size=1000)
        self.stdout.write(f"  - city routes replaced: {len(payload)}")

    def _replace_delivery_slabs(self, rows, courier_map, snapshot_ids):
        DeliverySlab.objects.filter(courier_id__in=snapshot_ids).delete()
        payload = [
            DeliverySlab(
                courier=self._resolve_courier(row["courier_code"], courier_map),
                min_weight=float(row["min_weight"]),
                max_weight=float(row["max_weight"]) if row["max_weight"] is not None else None,
                rate=Decimal(str(row["rate"])),
            )
            for row in rows
        ]
        for batch in iter_in_chunks(payload, 1000):
            DeliverySlab.objects.bulk_create(batch, batch_size=1000)
        self.stdout.write(f"  - delivery slabs replaced: {len(payload)}")

    def _replace_custom_zones(self, rows, courier_map, snapshot_ids):
        CustomZone.objects.filter(courier_id__in=snapshot_ids).delete()
        payload = [
            CustomZone(
                courier=self._resolve_courier(row["courier_code"], courier_map),
                location_name=row["location_name"],
                zone_code=row["zone_code"],
            )
            for row in rows
        ]
        for batch in iter_in_chunks(payload, 1000):
            CustomZone.objects.bulk_create(batch, batch_size=1000)
        self.stdout.write(f"  - custom zones replaced: {len(payload)}")

    def _replace_custom_zone_rates(self, rows, courier_map, snapshot_ids):
        CustomZoneRate.objects.filter(courier_id__in=snapshot_ids).delete()
        payload = [
            CustomZoneRate(
                courier=self._resolve_courier(row["courier_code"], courier_map),
                from_zone=row["from_zone"],
                to_zone=row["to_zone"],
                rate_per_kg=Decimal(str(row["rate_per_kg"])),
            )
            for row in rows
        ]
        for batch in iter_in_chunks(payload, 1000):
            CustomZoneRate.objects.bulk_create(batch, batch_size=1000)
        self.stdout.write(f"  - custom zone rates replaced: {len(payload)}")

    def _replace_pincodes(self, input_dir):
        Pincode.objects.all().delete()
        total = 0
        batch = []
        for row in read_jsonl_gz(input_dir / FILE_NAMES["pincodes"]):
            batch.append(
                Pincode(
                    pincode=int(row["pincode"]),
                    office_name=row["office_name"],
                    pincode_type=row.get("pincode_type"),
                    district=row["district"],
                    state=row["state"],
                    is_serviceable=bool(row["is_serviceable"]),
                )
            )
            if len(batch) >= 5000:
                Pincode.objects.bulk_create(batch, batch_size=5000)
                total += len(batch)
                batch = []
        if batch:
            Pincode.objects.bulk_create(batch, batch_size=5000)
            total += len(batch)
        self.stdout.write(f"  - pincodes replaced: {total}")

    def _replace_serviceable_pincodes(self, input_dir, courier_map, snapshot_ids):
        ServiceablePincode.objects.filter(courier_id__in=snapshot_ids).delete()
        total = 0
        batch = []
        for row in read_jsonl_gz(input_dir / FILE_NAMES["serviceable_pincodes"]):
            batch.append(
                ServiceablePincode(
                    courier=self._resolve_courier(row["courier_code"], courier_map),
                    pincode=int(row["pincode"]),
                    region_code=row.get("region_code"),
                    is_edl=bool(row["is_edl"]),
                    edl_distance=float(row["edl_distance"]),
                    is_cod_available=bool(row["is_cod_available"]),
                    is_prepaid_available=bool(row["is_prepaid_available"]),
                    is_pickup_available=bool(row["is_pickup_available"]),
                    is_embargo=bool(row["is_embargo"]),
                    city_name=row.get("city_name"),
                )
            )
            if len(batch) >= 5000:
                ServiceablePincode.objects.bulk_create(batch, batch_size=5000)
                total += len(batch)
                batch = []
        if batch:
            ServiceablePincode.objects.bulk_create(batch, batch_size=5000)
            total += len(batch)
        self.stdout.write(f"  - serviceable pincodes replaced: {total}")

    def _replace_ftl_rates(self, rows):
        FTLRate.objects.all().delete()
        payload = [
            FTLRate(
                source_city=row["source_city"],
                destination_city=row["destination_city"],
                truck_type=row["truck_type"],
                rate=Decimal(str(row["rate"])),
            )
            for row in rows
        ]
        for batch in iter_in_chunks(payload, 1000):
            FTLRate.objects.bulk_create(batch, batch_size=1000)
        self.stdout.write(f"  - ftl rates replaced: {len(payload)}")

    def _replace_zone_rules(self, rows):
        ZoneRule.objects.all().delete()
        payload = [
            ZoneRule(
                name=row["name"],
                rule_type=row["rule_type"],
                is_active=bool(row["is_active"]),
            )
            for row in rows
        ]
        for batch in iter_in_chunks(payload, 1000):
            ZoneRule.objects.bulk_create(batch, batch_size=1000)
        self.stdout.write(f"  - zone rules replaced: {len(payload)}")

    def _replace_location_aliases(self, rows):
        LocationAlias.objects.all().delete()
        payload = [
            LocationAlias(
                alias=row["alias"],
                standard_name=row["standard_name"],
                category=row["category"],
            )
            for row in rows
        ]
        for batch in iter_in_chunks(payload, 1000):
            LocationAlias.objects.bulk_create(batch, batch_size=1000)
        self.stdout.write(f"  - location aliases replaced: {len(payload)}")

    def _replace_system_config(self, payload):
        SystemConfig.objects.exclude(pk=1).delete()
        if not payload:
            SystemConfig.objects.filter(pk=1).delete()
            self.stdout.write("  - system config cleared")
            return
        SystemConfig.objects.update_or_create(
            pk=1,
            defaults={
                "diesel_price_current": Decimal(str(payload["diesel_price_current"])),
                "base_diesel_price": Decimal(str(payload["base_diesel_price"])),
                "fuel_surcharge_ratio": Decimal(str(payload["fuel_surcharge_ratio"])),
                "gst_rate": Decimal(str(payload["gst_rate"])),
                "escalation_rate": Decimal(str(payload["escalation_rate"])),
                "default_servicable_csv": payload["default_servicable_csv"],
            },
        )
        self.stdout.write("  - system config synced: 1")

    def _upsert_warehouses(self, rows):
        if not rows:
            self.stdout.write("  - courier warehouses skipped: 0 (snapshot file missing)")
            return

        synced = 0
        for row in rows:
            fields = row.get("fields", row)
            defaults = {
                "name": fields.get("name", ""),
                "contact_name": fields.get("contact_name", ""),
                "contact_no": fields.get("contact_no", ""),
                "address": fields.get("address", ""),
                "address_2": fields.get("address_2"),
                "pincode": fields.get("pincode", ""),
                "city": fields.get("city", ""),
                "state": fields.get("state", ""),
                "gst_number": fields.get("gst_number"),
                "shipdaak_pickup_id": fields.get("shipdaak_pickup_id"),
                "shipdaak_rto_id": fields.get("shipdaak_rto_id"),
                "shipdaak_synced_at": self._parse_datetime(fields.get("shipdaak_synced_at")),
                "is_active": bool(fields.get("is_active", True)),
            }

            lookup = {"pk": row["pk"]} if row.get("pk") is not None else {"name": defaults["name"]}
            Warehouse.objects.update_or_create(**lookup, defaults=defaults)
            synced += 1

        self.stdout.write(f"  - courier warehouses synced: {synced}")

    def _parse_datetime(self, value):
        if not value:
            return None
        if hasattr(value, "tzinfo"):
            return value
        parsed = parse_datetime(str(value))
        if parsed is None:
            raise CommandError(f"Invalid datetime in courier warehouse snapshot: {value}")
        return parsed

    def _resolve_courier(self, courier_code, courier_map):
        courier = courier_map.get(courier_code)
        if not courier:
            raise CommandError(f"Snapshot references unknown courier_code '{courier_code}'.")
        return courier
