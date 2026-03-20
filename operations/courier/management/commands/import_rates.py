import os
import re
from decimal import Decimal

import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction

from ...models import (
    CityRoute,
    Courier,
    CourierZoneRate,
    CustomZone,
    CustomZoneRate,
    DeliverySlab,
)


class Command(BaseCommand):
    help = "Import Courier rates/config from Excel or from cleaned CSV files."

    def add_arguments(self, parser):
        parser.add_argument("excel_path", nargs="?", type=str, help="Path to Excel file (legacy mode).")
        parser.add_argument("--master-csv", dest="master_csv", type=str, help="Path to Master Configuration CSV.")
        parser.add_argument("--zones-csv", dest="zones_csv", type=str, help="Path to Standard Zone Rates CSV.")

    def __init__(self):
        super().__init__()
        # (display_name, mode, service_category, min_weight) -> Courier
        self._courier_key_map = {}

    def _clean_decimal(self, val):
        if pd.isna(val):
            return Decimal("0.00")

        s = str(val).strip()
        if not s:
            return Decimal("0.00")
        if s.lower() in {"na", "n/a", "-", "--", "null", "none", "₹ -", "? -"}:
            return Decimal("0.00")

        s = s.replace("₹", "").replace("â‚¹", "").replace("%", "").replace(",", "").strip()
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        if not m:
            return Decimal("0.00")

        try:
            return Decimal(m.group(0))
        except Exception:
            return Decimal("0.00")

    def _clean_bool(self, val):
        if pd.isna(val):
            return False
        return str(val).strip().lower() in {"true", "yes", "1", "y", "t"}

    def _clean_weight(self, val, default=0.5):
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return default
        s = str(val).strip()
        for suffix in ("kgs", "kg", "gms", "gm", "g"):
            if s.lower().endswith(suffix):
                s = s[: -len(suffix)].strip()
                break
        try:
            return float(s)
        except ValueError:
            return default

    def _norm_text(self, value):
        return " ".join(str(value or "").strip().lower().split())

    def _norm_weight(self, value):
        return round(self._clean_weight(value, default=0.0), 4)

    def _norm_service_category(self, value):
        raw = self._norm_text(value)
        mapping = {
            "surface": Courier.ServiceCategory.SURFACE,
            "air": Courier.ServiceCategory.AIR,
            "heavy surface": Courier.ServiceCategory.HEAVY_SURFACE,
            "documents": Courier.ServiceCategory.DOCUMENTS,
            "ndd surface": Courier.ServiceCategory.NDD_SURFACE,
            "ndd heavy surface": Courier.ServiceCategory.NDD_HEAVY_SURFACE,
            "rvp": Courier.ServiceCategory.RVP,
        }
        return mapping.get(raw, str(value).strip() if value is not None else Courier.ServiceCategory.SURFACE)

    def _build_courier_key(self, display_name, mode, service_category, min_weight):
        return (
            self._norm_text(display_name),
            self._norm_text(mode),
            self._norm_text(service_category),
            self._norm_weight(min_weight),
        )

    def _find_sheet_name(self, xls, desired_name):
        target = self._norm_text(desired_name)
        return next((s for s in xls.sheet_names if self._norm_text(s) == target), None)

    def _col(self, row, *keys, default=None):
        for k in keys:
            v = row.get(k.strip().lower())
            if v is not None and not (isinstance(v, float) and pd.isna(v)):
                return v
        return default

    def _build_courier_name(self, aggregator, display_name, service_category, min_weight):
        weight_str = f"{self._norm_weight(min_weight):g}"
        return f"{aggregator} {display_name} {service_category} {weight_str}"

    def _make_unique_internal_name(self, base_name, current_courier_id=None):
        base = base_name.strip()
        candidate = base[:100]
        i = 2
        while True:
            conflict = Courier.objects.filter(name=candidate)
            if current_courier_id:
                conflict = conflict.exclude(id=current_courier_id)
            if not conflict.exists():
                break
            suffix = f" ({i})"
            candidate = (base[: max(1, 100 - len(suffix))] + suffix)
            i += 1
        return candidate

    def handle(self, *args, **kwargs):
        excel_path = kwargs.get("excel_path")
        master_csv = kwargs.get("master_csv")
        zones_csv = kwargs.get("zones_csv")

        try:
            with transaction.atomic():
                if master_csv or zones_csv:
                    self._import_from_csv(master_csv, zones_csv)
                else:
                    if not excel_path:
                        self.stdout.write(
                            self.style.ERROR("Provide either excel_path or both --master-csv and --zones-csv.")
                        )
                        return
                    if not os.path.exists(excel_path):
                        self.stdout.write(self.style.ERROR(f"File not found: {excel_path}"))
                        return

                    self.stdout.write(self.style.SUCCESS(f"Reading Excel file: {excel_path}"))
                    xls = pd.ExcelFile(excel_path)
                    self.process_master_config(xls)
                    self.process_standard_zones(xls)
                    self.process_custom_zones_mapping(xls)
                    self.process_custom_zones_matrix(xls)
                    self.process_city_to_city(xls)

            self.stdout.write(self.style.SUCCESS("Successfully imported all rates!"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Import failed: {str(e)}"))
            import traceback

            traceback.print_exc()

    def _import_from_csv(self, master_csv, zones_csv):
        if not master_csv or not zones_csv:
            raise ValueError("CSV mode requires both --master-csv and --zones-csv")
        if not os.path.exists(master_csv):
            raise FileNotFoundError(f"Master CSV not found: {master_csv}")
        if not os.path.exists(zones_csv):
            raise FileNotFoundError(f"Zones CSV not found: {zones_csv}")

        self.stdout.write(self.style.SUCCESS(f"Reading Master CSV: {master_csv}"))
        self.process_master_config_df(pd.read_csv(master_csv))

        self.stdout.write(self.style.SUCCESS(f"Reading Zones CSV: {zones_csv}"))
        self.process_standard_zones_df(pd.read_csv(zones_csv))

    def process_master_config(self, xls):
        sheet_name = self._find_sheet_name(xls, "Master Configuration")
        if not sheet_name:
            self.stdout.write(self.style.WARNING("Sheet 'Master Configuration' not found. Skipping config..."))
            return
        self.stdout.write(f"Processing '{sheet_name}'...")
        self.process_master_config_df(pd.read_excel(xls, sheet_name=sheet_name))

    def process_master_config_df(self, df):
        self._courier_key_map = {}

        df.columns = [str(c).strip().lower() for c in df.columns]
        self.stdout.write(f"  Normalised columns: {list(df.columns)}")

        rows_processed = 0
        rows_errored = 0

        for index, row in df.iterrows():
            courier_name_raw = self._col(row, "courier name", "carrier name", "courier")
            if courier_name_raw is None or pd.isna(courier_name_raw):
                continue
            courier_name = str(courier_name_raw).strip()
            if not courier_name or courier_name.lower() == "nan":
                continue

            try:
                agg_raw = self._col(row, "aggregator")
                aggregator = str(agg_raw).strip() if agg_raw is not None else Courier.Aggregator.STANDALONE
                if aggregator not in [c[0] for c in Courier.Aggregator.choices]:
                    aggregator = Courier.Aggregator.STANDALONE

                carrier_type = self._col(row, "carrier type", "carrier type (b2c, b2b)", default="B2C")
                carrier_mode = self._col(row, "carrier mode", "carrier mode (surface, air)", default="Surface")
                service_raw = self._col(
                    row,
                    "service category",
                    "service category (surface, air, ndd, documents, etc.)",
                    default=Courier.ServiceCategory.SURFACE,
                )
                service_category = self._norm_service_category(service_raw)

                min_w_raw = self._col(row, "min weight kg", "min weight (kg)", "min. weight")
                max_w_raw = self._col(row, "max weight kg", "max weight (kg)", "max. weight")
                vol_raw = self._col(row, "volumetric divisor")
                logic_raw = self._col(
                    row,
                    "rate logic",
                    "rate logic (zonal_standard, zonal_custom, city_to_city)",
                    default="Zonal_Standard",
                )
                fuel_dynamic_raw = self._col(row, "fuel is dynamic", "fuel is dynamic (true/false)")

                min_weight = self._clean_weight(min_w_raw, default=0.5)
                max_weight = self._clean_weight(max_w_raw, default=99999.0)
                volumetric_divisor = int(float(vol_raw)) if vol_raw is not None and not pd.isna(vol_raw) else 5000
                rate_logic = str(logic_raw).strip() if logic_raw is not None else "Zonal_Standard"

                defaults = {
                    "aggregator": aggregator,
                    "display_name": courier_name,
                    "carrier_type": str(carrier_type).strip() if carrier_type else "B2C",
                    "carrier_mode": str(carrier_mode).strip() if carrier_mode else "Surface",
                    "service_category": str(service_category).strip() if service_category else Courier.ServiceCategory.SURFACE,
                    "is_active": True,
                    "min_weight": min_weight,
                    "max_weight": max_weight,
                    "volumetric_divisor": volumetric_divisor,
                    "rate_logic": rate_logic,
                    "docket_fee": self._clean_decimal(self._col(row, "docket fee")),
                    "eway_bill_fee": self._clean_decimal(self._col(row, "eway bill fee")),
                    "cod_charge_fixed": self._clean_decimal(self._col(row, "cod charge fixed")),
                    "cod_charge_percent": self._clean_decimal(self._col(row, "cod charge percent")),
                    "hamali_per_kg": self._clean_decimal(self._col(row, "hamali per kg")),
                    "min_hamali": self._clean_decimal(self._col(row, "min hamali")),
                    "fov_min": self._clean_decimal(self._col(row, "fov min fee")),
                    "fov_insured_percent": self._clean_decimal(self._col(row, "fov insured percent")),
                    "other_charges": self._clean_decimal(self._col(row, "other charges")),
                    "fuel_is_dynamic": self._clean_bool(fuel_dynamic_raw),
                    "fuel_base_price": self._clean_decimal(self._col(row, "fuel base price")),
                    "fuel_ratio": self._clean_decimal(self._col(row, "fuel ratio")),
                    "fuel_surcharge_percent": self._clean_decimal(self._col(row, "fuel surcharge percent")),
                }

                key = self._build_courier_key(
                    courier_name,
                    defaults["carrier_mode"],
                    defaults["service_category"],
                    defaults["min_weight"],
                )
                other_charges_val = defaults.pop("other_charges")

                courier = (
                    Courier.objects.filter(
                        aggregator=defaults["aggregator"],
                        display_name__iexact=courier_name,
                        carrier_mode__iexact=defaults["carrier_mode"],
                        service_category__iexact=defaults["service_category"],
                        constraints_config__min_weight=defaults["min_weight"],
                    )
                    .first()
                )

                if courier:
                    target_name = self._build_courier_name(
                        defaults["aggregator"],
                        defaults["display_name"],
                        defaults["service_category"],
                        defaults["min_weight"],
                    )
                    courier.name = self._make_unique_internal_name(target_name, current_courier_id=courier.id)
                    for k, v in defaults.items():
                        try:
                            setattr(courier, k, v)
                        except Exception as attr_e:
                            self.stdout.write(
                                self.style.WARNING(f"    setattr({courier_name}, {k}, {v}): {attr_e}")
                            )
                    courier.save()
                else:
                    base_name = self._build_courier_name(
                        defaults["aggregator"],
                        defaults["display_name"],
                        defaults["service_category"],
                        defaults["min_weight"],
                    )
                    courier = Courier.objects.create(name=self._make_unique_internal_name(base_name), **defaults)

                courier.other_charges = other_charges_val
                self._courier_key_map[key] = courier
                rows_processed += 1
                self.stdout.write(f"  [{index}] Processed: {courier_name}")
            except Exception as row_e:
                rows_errored += 1
                self.stdout.write(self.style.ERROR(f"  ERROR at row {index} ({courier_name}): {row_e}"))

        self.stdout.write(self.style.SUCCESS(f"  Master Config done: {rows_processed} saved, {rows_errored} errors."))

    def process_standard_zones(self, xls):
        sheet_name = self._find_sheet_name(xls, "Standard Zone Rates")
        if not sheet_name:
            self.stdout.write(self.style.WARNING("Sheet 'Standard Zone Rates' not found. Skipping standard zones."))
            return
        self.stdout.write(f"Processing '{sheet_name}'...")
        self.process_standard_zones_df(pd.read_excel(xls, sheet_name=sheet_name))

    def process_standard_zones_df(self, df):
        df.columns = [str(c).strip().lower() for c in df.columns]
        self.stdout.write(f"  Columns after normalise: {list(df.columns)}")

        courier_col = next((c for c in df.columns if c in ("courier", "carrier", "courier name", "carrier name")), None)
        if not courier_col:
            self.stdout.write(self.style.ERROR("  Cannot find courier/carrier column in Standard Zone Rates."))
            return

        type_col = next((c for c in df.columns if c.replace(" ", "") == "typename"), "type name")
        mode_col = next((c for c in df.columns if c in ("mode", "carrier mode")), "mode")
        service_col = next((c for c in df.columns if c in ("service name", "service category")), None)
        min_w_col = next((c for c in df.columns if c in ("min. weight", "min weight", "min_weight")), "min. weight")

        type_mapping = {
            "forward": CourierZoneRate.RateType.FORWARD,
            "fwd": CourierZoneRate.RateType.FORWARD,
            "forward_rates": CourierZoneRate.RateType.FORWARD,
            "additional": CourierZoneRate.RateType.ADDITIONAL,
            "additional_rates": CourierZoneRate.RateType.ADDITIONAL,
            "fwd additional": CourierZoneRate.RateType.ADDITIONAL,
            "fwd additonal": CourierZoneRate.RateType.ADDITIONAL,
            "fwdadditonal": CourierZoneRate.RateType.ADDITIONAL,
            "additonal": CourierZoneRate.RateType.ADDITIONAL,
            "rto": CourierZoneRate.RateType.RTO,
            "rto additional": CourierZoneRate.RateType.RTO_ADDITIONAL,
            "rto additonal": CourierZoneRate.RateType.RTO_ADDITIONAL,
            "rtoadditonal": CourierZoneRate.RateType.RTO_ADDITIONAL,
            "reverse": CourierZoneRate.RateType.REVERSE,
            "return": CourierZoneRate.RateType.REVERSE,
            "reverse additional": CourierZoneRate.RateType.REVERSE_ADDITIONAL,
        }

        rows_ok = 0
        rows_skipped = 0
        rate_cells_written = 0

        for index, row in df.iterrows():
            courier_name = str(row.get(courier_col, "")).strip()
            type_name = str(row.get(type_col, "")).strip().lower()
            if not courier_name or courier_name.lower() == "nan" or not type_name or type_name == "nan":
                rows_skipped += 1
                continue

            mode_name = str(row.get(mode_col, "Surface")).strip() or "Surface"
            service_name = (
                str(row.get(service_col, "Surface")).strip()
                if service_col
                else Courier.ServiceCategory.SURFACE
            )
            min_weight = self._clean_weight(row.get(min_w_col, 0.5), default=0.5)
            key = self._build_courier_key(courier_name, mode_name, service_name, min_weight)

            courier = self._courier_key_map.get(key)
            if not courier:
                courier = (
                    Courier.objects.filter(
                        display_name__iexact=courier_name,
                        carrier_mode__iexact=mode_name,
                        service_category__iexact=self._norm_service_category(service_name),
                        constraints_config__min_weight=min_weight,
                    )
                    .first()
                )
            if not courier:
                courier = Courier.objects.filter(name__iexact=courier_name).first()
            if not courier:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Courier not found row {index}: {courier_name}/{mode_name}/{service_name}/{min_weight}"
                    )
                )
                rows_skipped += 1
                continue

            db_rate_type = type_mapping.get(type_name)
            if not db_rate_type:
                self.stdout.write(self.style.WARNING(f"  Unknown Type Name '{type_name}' for '{courier_name}'."))
                rows_skipped += 1
                continue

            for col in df.columns:
                if not col.startswith("z_"):
                    continue
                raw_val = row.get(col)
                if pd.isna(raw_val) or str(raw_val).strip() == "":
                    continue
                rate_val = self._clean_decimal(raw_val)
                CourierZoneRate.objects.update_or_create(
                    courier=courier,
                    zone_code=col,
                    rate_type=db_rate_type,
                    defaults={"rate": rate_val},
                )
                rate_cells_written += 1

            rows_ok += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"  Standard Zones done: {rows_ok} rows -> {rate_cells_written} rate cells written, {rows_skipped} skipped."
            )
        )

    def process_custom_zones_mapping(self, xls):
        sheet_name = self._find_sheet_name(xls, "Custom Zones Mapping")
        if not sheet_name:
            sheet_name = self._find_sheet_name(xls, "Custom Zones (Mapping)")
        if not sheet_name:
            return

        self.stdout.write(f"Processing '{sheet_name}'...")
        df = pd.read_excel(xls, sheet_name=sheet_name)

        for _, row in df.iterrows():
            courier_name = str(row.get("Courier Name", "")).strip()
            loc_name = str(row.get("Location Name", "")).strip()
            zone_code = str(row.get("Zone Code", "")).strip()
            if not courier_name or courier_name == "nan" or not loc_name or loc_name == "nan":
                continue
            courier = Courier.objects.filter(name=courier_name).first() or Courier.objects.filter(
                display_name__iexact=courier_name
            ).first()
            if not courier:
                continue
            CustomZone.objects.update_or_create(
                courier=courier,
                location_name=loc_name,
                defaults={"zone_code": zone_code},
            )

    def process_custom_zones_matrix(self, xls):
        sheet_name = self._find_sheet_name(xls, "Custom Zone Rates (Matrix)")
        if not sheet_name:
            sheet_name = self._find_sheet_name(xls, "Custom Zones (Matrix)")
        if not sheet_name:
            return

        self.stdout.write(f"Processing '{sheet_name}'...")
        df = pd.read_excel(xls, sheet_name=sheet_name)

        for _, row in df.iterrows():
            courier_name = str(row.get("Courier Name", "")).strip()
            from_zone = str(row.get("From Zone", "")).strip()
            to_zone = str(row.get("To Zone", "")).strip()
            rate = row.get("Rate Per Kg")
            if not courier_name or courier_name == "nan" or not from_zone or from_zone == "nan" or pd.isna(rate):
                continue
            courier = Courier.objects.filter(name=courier_name).first() or Courier.objects.filter(
                display_name__iexact=courier_name
            ).first()
            if not courier:
                continue
            CustomZoneRate.objects.update_or_create(
                courier=courier,
                from_zone=from_zone,
                to_zone=to_zone,
                defaults={"rate_per_kg": self._clean_decimal(rate)},
            )

    def process_city_to_city(self, xls):
        sheet_name = self._find_sheet_name(xls, "City to City")
        if not sheet_name:
            return

        self.stdout.write(f"Processing '{sheet_name}'...")
        df = pd.read_excel(xls, sheet_name=sheet_name)
        flat_rate_col = next((col for col in df.columns if "Flat Slab Rate" in str(col)), None)

        for _, row in df.iterrows():
            courier_name = str(row.get("Courier Name", "")).strip()
            if not courier_name or courier_name == "nan":
                continue

            courier = Courier.objects.filter(name=courier_name).first() or Courier.objects.filter(
                display_name__iexact=courier_name
            ).first()
            if not courier:
                continue

            dest_city = str(row.get("Destination City", "")).strip()
            rate_kg = row.get("Rate Per Kg")
            if dest_city and dest_city != "nan" and not pd.isna(rate_kg):
                CityRoute.objects.update_or_create(
                    courier=courier,
                    city_name=dest_city,
                    defaults={"rate_per_kg": self._clean_decimal(rate_kg)},
                )

            min_w = row.get("Min Weight Slab")
            max_w = row.get("Max Weight Slab")
            if not pd.isna(min_w):
                flat_rate = row.get(flat_rate_col) if flat_rate_col else None
                if flat_rate is not None and not pd.isna(flat_rate):
                    DeliverySlab.objects.update_or_create(
                        courier=courier,
                        min_weight=float(min_w),
                        defaults={
                            "max_weight": float(max_w) if not pd.isna(max_w) else None,
                            "rate": self._clean_decimal(flat_rate),
                        },
                    )
