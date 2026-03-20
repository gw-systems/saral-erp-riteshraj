from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

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
from ...snapshot_utils import (
    FILE_NAMES,
    SNAPSHOT_VERSION,
    default_snapshot_dir,
    ensure_snapshot_dir,
    file_sha256,
    write_json,
    write_jsonl,
    write_jsonl_gz,
)


class Command(BaseCommand):
    help = "Export the current courier master/reference data into a portable snapshot package."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            dest="output_dir",
            help="Directory to write the snapshot package into.",
        )

    def handle(self, *args, **options):
        output_dir = ensure_snapshot_dir(
            options.get("output_dir") or default_snapshot_dir(settings.BASE_DIR)
        )
        self.stdout.write(f"Writing courier snapshot to: {output_dir}")

        file_meta = {}

        self._write_list_file(
            output_dir,
            "couriers",
            self._export_couriers(),
            file_meta,
        )
        self._write_list_file(
            output_dir,
            "fee_structures",
            self._export_fee_structures(),
            file_meta,
        )
        self._write_list_file(
            output_dir,
            "service_constraints",
            self._export_service_constraints(),
            file_meta,
        )
        self._write_list_file(
            output_dir,
            "fuel_configurations",
            self._export_fuel_configurations(),
            file_meta,
        )
        self._write_list_file(
            output_dir,
            "routing_logics",
            self._export_routing_logics(),
            file_meta,
        )
        self._write_jsonl_file(
            output_dir,
            "courier_zone_rates",
            self._iter_courier_zone_rates(),
            file_meta,
        )
        self._write_list_file(
            output_dir,
            "city_routes",
            self._export_city_routes(),
            file_meta,
        )
        self._write_list_file(
            output_dir,
            "delivery_slabs",
            self._export_delivery_slabs(),
            file_meta,
        )
        self._write_list_file(
            output_dir,
            "custom_zones",
            self._export_custom_zones(),
            file_meta,
        )
        self._write_list_file(
            output_dir,
            "custom_zone_rates",
            self._export_custom_zone_rates(),
            file_meta,
        )
        self._write_jsonl_gz_file(
            output_dir,
            "pincodes",
            self._iter_pincodes(),
            file_meta,
        )
        self._write_jsonl_gz_file(
            output_dir,
            "serviceable_pincodes",
            self._iter_serviceable_pincodes(),
            file_meta,
        )
        self._write_list_file(
            output_dir,
            "ftl_rates",
            self._export_ftl_rates(),
            file_meta,
        )
        self._write_list_file(
            output_dir,
            "zone_rules",
            self._export_zone_rules(),
            file_meta,
        )
        self._write_list_file(
            output_dir,
            "location_aliases",
            self._export_location_aliases(),
            file_meta,
        )
        self._write_object_file(
            output_dir,
            "system_config",
            self._export_system_config(),
            file_meta,
        )
        self._write_list_file(
            output_dir,
            "courier_warehouses",
            self._export_courier_warehouses(),
            file_meta,
        )

        manifest = {
            "snapshot_version": SNAPSHOT_VERSION,
            "exported_at": timezone.now().isoformat(),
            "source_app": "courier",
            "counts": {key: meta["record_count"] for key, meta in file_meta.items()},
            "files": {
                FILE_NAMES[key]: {
                    "dataset": key,
                    "record_count": meta["record_count"],
                    "sha256": meta["sha256"],
                }
                for key, meta in file_meta.items()
            },
        }
        write_json(output_dir / FILE_NAMES["manifest"], manifest)

        self.stdout.write(self.style.SUCCESS("Courier snapshot export completed successfully."))

    def _write_list_file(self, output_dir, dataset_key, records, file_meta):
        path = output_dir / FILE_NAMES[dataset_key]
        write_json(path, records)
        file_meta[dataset_key] = {
            "record_count": len(records),
            "sha256": file_sha256(path),
        }
        self.stdout.write(f"  - {dataset_key}: {len(records)} rows")

    def _write_object_file(self, output_dir, dataset_key, payload, file_meta):
        path = output_dir / FILE_NAMES[dataset_key]
        write_json(path, payload)
        file_meta[dataset_key] = {
            "record_count": 1 if payload else 0,
            "sha256": file_sha256(path),
        }
        self.stdout.write(f"  - {dataset_key}: {file_meta[dataset_key]['record_count']} row")

    def _write_jsonl_file(self, output_dir, dataset_key, records, file_meta):
        path = output_dir / FILE_NAMES[dataset_key]
        count = write_jsonl(path, records)
        file_meta[dataset_key] = {
            "record_count": count,
            "sha256": file_sha256(path),
        }
        self.stdout.write(f"  - {dataset_key}: {count} rows")

    def _write_jsonl_gz_file(self, output_dir, dataset_key, records, file_meta):
        path = output_dir / FILE_NAMES[dataset_key]
        count = write_jsonl_gz(path, records)
        file_meta[dataset_key] = {
            "record_count": count,
            "sha256": file_sha256(path),
        }
        self.stdout.write(f"  - {dataset_key}: {count} rows")

    def _export_couriers(self):
        return [
            {
                "courier_code": courier.courier_code,
                "name": courier.name,
                "display_name": courier.display_name,
                "aggregator": courier.aggregator,
                "carrier_type": courier.carrier_type,
                "carrier_mode": courier.carrier_mode,
                "service_category": courier.service_category,
                "is_active": courier.is_active,
                "shipdaak_courier_id": courier.shipdaak_courier_id,
                "legacy_rate_card_backup": courier.legacy_rate_card_backup,
            }
            for courier in Courier.objects.order_by("courier_code")
        ]

    def _export_fee_structures(self):
        return [
            {
                "courier_code": item.courier_link.courier_code,
                "docket_fee": item.docket_fee,
                "eway_bill_fee": item.eway_bill_fee,
                "appointment_delivery_fee": item.appointment_delivery_fee,
                "cod_fixed": item.cod_fixed,
                "cod_percent": item.cod_percent,
                "hamali_per_kg": item.hamali_per_kg,
                "min_hamali": item.min_hamali,
                "fov_min": item.fov_min,
                "fov_insured_percent": item.fov_insured_percent,
                "fov_uninsured_percent": item.fov_uninsured_percent,
                "damage_claim_percent": item.damage_claim_percent,
                "other_charges": item.other_charges,
            }
            for item in FeeStructure.objects.select_related("courier_link").order_by(
                "courier_link__courier_code"
            )
        ]

    def _export_service_constraints(self):
        return [
            {
                "courier_code": item.courier_link.courier_code,
                "min_weight": item.min_weight,
                "max_weight": item.max_weight,
                "volumetric_divisor": item.volumetric_divisor,
                "required_source_city": item.required_source_city,
            }
            for item in ServiceConstraints.objects.select_related("courier_link").order_by(
                "courier_link__courier_code"
            )
        ]

    def _export_fuel_configurations(self):
        return [
            {
                "courier_code": item.courier_link.courier_code,
                "is_dynamic": item.is_dynamic,
                "base_price": item.base_price,
                "ratio": item.ratio,
                "surcharge_percent": item.surcharge_percent,
            }
            for item in FuelConfiguration.objects.select_related("courier_link").order_by(
                "courier_link__courier_code"
            )
        ]

    def _export_routing_logics(self):
        return [
            {
                "courier_code": item.courier_link.courier_code,
                "logic_type": item.logic_type,
                "serviceable_pincode_csv": item.serviceable_pincode_csv,
                "hub_city": item.hub_city,
                "hub_pincode_prefixes": item.hub_pincode_prefixes,
            }
            for item in RoutingLogic.objects.select_related("courier_link").order_by(
                "courier_link__courier_code"
            )
        ]

    def _iter_courier_zone_rates(self):
        queryset = CourierZoneRate.objects.select_related("courier").order_by(
            "courier__courier_code",
            "zone_code",
            "rate_type",
        )
        for item in queryset.iterator(chunk_size=2000):
            yield {
                "courier_code": item.courier.courier_code,
                "zone_code": item.zone_code,
                "rate_type": item.rate_type,
                "rate": item.rate,
            }

    def _export_city_routes(self):
        return [
            {
                "courier_code": item.courier.courier_code,
                "city_name": item.city_name,
                "rate_per_kg": item.rate_per_kg,
            }
            for item in CityRoute.objects.select_related("courier").order_by(
                "courier__courier_code",
                "city_name",
            )
        ]

    def _export_delivery_slabs(self):
        return [
            {
                "courier_code": item.courier.courier_code,
                "min_weight": item.min_weight,
                "max_weight": item.max_weight,
                "rate": item.rate,
            }
            for item in DeliverySlab.objects.select_related("courier").order_by(
                "courier__courier_code",
                "min_weight",
                "max_weight",
            )
        ]

    def _export_custom_zones(self):
        return [
            {
                "courier_code": item.courier.courier_code,
                "location_name": item.location_name,
                "zone_code": item.zone_code,
            }
            for item in CustomZone.objects.select_related("courier").order_by(
                "courier__courier_code",
                "zone_code",
                "location_name",
            )
        ]

    def _export_custom_zone_rates(self):
        return [
            {
                "courier_code": item.courier.courier_code,
                "from_zone": item.from_zone,
                "to_zone": item.to_zone,
                "rate_per_kg": item.rate_per_kg,
            }
            for item in CustomZoneRate.objects.select_related("courier").order_by(
                "courier__courier_code",
                "from_zone",
                "to_zone",
            )
        ]

    def _iter_pincodes(self):
        queryset = Pincode.objects.order_by("pincode")
        for item in queryset.iterator(chunk_size=5000):
            yield {
                "pincode": item.pincode,
                "office_name": item.office_name,
                "pincode_type": item.pincode_type,
                "district": item.district,
                "state": item.state,
                "is_serviceable": item.is_serviceable,
            }

    def _iter_serviceable_pincodes(self):
        queryset = ServiceablePincode.objects.select_related("courier").order_by(
            "courier__courier_code",
            "pincode",
        )
        for item in queryset.iterator(chunk_size=5000):
            yield {
                "courier_code": item.courier.courier_code,
                "pincode": item.pincode,
                "region_code": item.region_code,
                "is_edl": item.is_edl,
                "edl_distance": item.edl_distance,
                "is_cod_available": item.is_cod_available,
                "is_prepaid_available": item.is_prepaid_available,
                "is_pickup_available": item.is_pickup_available,
                "is_embargo": item.is_embargo,
                "city_name": item.city_name,
            }

    def _export_ftl_rates(self):
        return [
            {
                "source_city": item.source_city,
                "destination_city": item.destination_city,
                "truck_type": item.truck_type,
                "rate": item.rate,
            }
            for item in FTLRate.objects.order_by("source_city", "destination_city", "truck_type")
        ]

    def _export_zone_rules(self):
        return [
            {
                "name": item.name,
                "rule_type": item.rule_type,
                "is_active": item.is_active,
            }
            for item in ZoneRule.objects.order_by("rule_type", "name")
        ]

    def _export_location_aliases(self):
        return [
            {
                "alias": item.alias,
                "standard_name": item.standard_name,
                "category": item.category,
            }
            for item in LocationAlias.objects.order_by("category", "alias")
        ]

    def _export_system_config(self):
        config = SystemConfig.objects.order_by("pk").first()
        if not config:
            return None
        return {
            "diesel_price_current": config.diesel_price_current,
            "base_diesel_price": config.base_diesel_price,
            "fuel_surcharge_ratio": config.fuel_surcharge_ratio,
            "gst_rate": config.gst_rate,
            "escalation_rate": config.escalation_rate,
            "default_servicable_csv": config.default_servicable_csv,
        }

    def _export_courier_warehouses(self):
        return [
            {
                "model": "courier.warehouse",
                "pk": item.pk,
                "fields": {
                    "name": item.name,
                    "contact_name": item.contact_name,
                    "contact_no": item.contact_no,
                    "address": item.address,
                    "address_2": item.address_2,
                    "pincode": item.pincode,
                    "city": item.city,
                    "state": item.state,
                    "gst_number": item.gst_number,
                    "shipdaak_pickup_id": item.shipdaak_pickup_id,
                    "shipdaak_rto_id": item.shipdaak_rto_id,
                    "shipdaak_synced_at": item.shipdaak_synced_at,
                    "is_active": item.is_active,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                },
            }
            for item in Warehouse.objects.order_by("id")
        ]
