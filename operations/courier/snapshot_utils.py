import gzip
import hashlib
import json
from decimal import Decimal
from pathlib import Path


SNAPSHOT_VERSION = 1
DEFAULT_SNAPSHOT_DIRNAME = "bootstrap"

FILE_NAMES = {
    "manifest": "manifest.json",
    "couriers": "couriers.json",
    "courier_warehouses": "courier_warehouses.json",
    "fee_structures": "fee_structures.json",
    "service_constraints": "service_constraints.json",
    "fuel_configurations": "fuel_configurations.json",
    "routing_logics": "routing_logics.json",
    "courier_zone_rates": "courier_zone_rates.jsonl",
    "city_routes": "city_routes.json",
    "delivery_slabs": "delivery_slabs.json",
    "custom_zones": "custom_zones.json",
    "custom_zone_rates": "custom_zone_rates.json",
    "pincodes": "pincodes.jsonl.gz",
    "serviceable_pincodes": "serviceable_pincodes.jsonl.gz",
    "ftl_rates": "ftl_rates.json",
    "zone_rules": "zone_rules.json",
    "location_aliases": "location_aliases.json",
    "system_config": "system_config.json",
}


def default_snapshot_dir(base_dir) -> Path:
    app_dir = Path(__file__).resolve().parent
    return app_dir / DEFAULT_SNAPSHOT_DIRNAME


def ensure_snapshot_dir(path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def serialize_snapshot_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: serialize_snapshot_value(val) for key, val in value.items()}
    if isinstance(value, list):
        return [serialize_snapshot_value(item) for item in value]
    if isinstance(value, tuple):
        return [serialize_snapshot_value(item) for item in value]
    return value


def write_json(path, payload) -> None:
    Path(path).write_text(
        json.dumps(serialize_snapshot_value(payload), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_jsonl(path, records) -> int:
    count = 0
    with Path(path).open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(serialize_snapshot_value(record), sort_keys=True))
            handle.write("\n")
            count += 1
    return count


def read_jsonl(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl_gz(path, records) -> int:
    count = 0
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(serialize_snapshot_value(record), sort_keys=True))
            handle.write("\n")
            count += 1
    return count


def read_jsonl_gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def file_sha256(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_in_chunks(iterable, size):
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch
