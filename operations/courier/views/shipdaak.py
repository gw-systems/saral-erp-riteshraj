"""Operational Shipdaak endpoints backed by direct Shipdaak APIs."""

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..integrations import ShipdaakV2Client
from ..integrations.errors import ShipdaakIntegrationError
from ..models import Order, Warehouse
from ..permissions import IsAdminToken
from ..services import ShipdaakLifecycleService


def _extract_warehouse_ids(payload: dict) -> tuple[int | None, int | None]:
    pickup_id = payload.get("pickupId")
    rto_id = payload.get("rtoId")
    if pickup_id and rto_id:
        return pickup_id, rto_id

    nested = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return nested.get("pickup_warehouse_id"), nested.get("rto_warehouse_id")


def _normalize_warehouse_name(name: str) -> str:
    return str(name).strip().casefold()


def _courier_warehouse_aliases(warehouse: Warehouse) -> dict[str, object]:
    return {
        "courierWarehouseId": warehouse.id,
        "courier_warehouse_id": warehouse.id,
        "courierWarehouseName": warehouse.name,
        "courier_warehouse_name": warehouse.name,
    }


def _with_courier_warehouse_aliases(payload: dict[str, object], warehouse: Warehouse) -> dict[str, object]:
    response = dict(payload)
    response.update(_courier_warehouse_aliases(warehouse))
    return response


def _validate_bulk_warehouse_row(row: object) -> tuple[dict[str, str | None] | None, str | None]:
    if not isinstance(row, dict):
        return None, "Each item must be a JSON object."

    required_fields = ("name", "contact_name", "contact_no", "address", "pincode", "city", "state")
    normalized: dict[str, str | None] = {}
    for field in required_fields:
        value = row.get(field)
        text = str(value).strip() if value is not None else ""
        if not text:
            return None, f"{field} is required."
        normalized[field] = text

    normalized["address_2"] = str(row.get("address_2", "")).strip() or None
    normalized["gst_number"] = str(row.get("gst_number", "")).strip() or None
    return normalized, None


def _max_bulk_orders() -> int:
    raw_limit = getattr(settings, "SHIPDAAK_LIVE_BULK_MAX_ORDERS", 50)
    try:
        parsed = int(raw_limit)
    except (TypeError, ValueError):
        parsed = 50
    return parsed if parsed > 0 else 50


def _extract_url(payload: object, keys: tuple[str, ...]) -> str:
    if isinstance(payload, str):
        value = payload.strip()
        return value if value.startswith(("http://", "https://")) else ""
    if not isinstance(payload, dict):
        return ""

    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            candidate = value.strip()
            if candidate.startswith(("http://", "https://")):
                return candidate
    return ""


# ---------------------------------------------------------------------------
# Courier warehouse management
# ---------------------------------------------------------------------------

@api_view(["POST"])
@permission_classes([IsAdminToken])
def shipdaak_import_existing_warehouse(request, pk: int):
    """Register a courier warehouse in ShipDaak using its raw address details."""
    try:
        warehouse = Warehouse.objects.get(pk=pk)
    except Warehouse.DoesNotExist:
        return Response({"detail": "Courier warehouse not found."}, status=status.HTTP_404_NOT_FOUND)

    client = ShipdaakV2Client()
    try:
        payload = client.create_warehouse(
            warehouse_name=warehouse.name,
            contact_name=warehouse.contact_name,
            contact_no=warehouse.contact_no,
            address=warehouse.address,
            address_2=warehouse.address_2,
            pin_code=str(warehouse.pincode),
            city=warehouse.city,
            state=warehouse.state,
            gst_number=warehouse.gst_number,
        )
        pickup_id, rto_id = _extract_warehouse_ids(payload if isinstance(payload, dict) else {})
        if pickup_id and rto_id:
            warehouse.shipdaak_pickup_id = pickup_id
            warehouse.shipdaak_rto_id = rto_id
            warehouse.shipdaak_synced_at = timezone.now()
            warehouse.save(
                update_fields=[
                    "shipdaak_pickup_id",
                    "shipdaak_rto_id",
                    "shipdaak_synced_at",
                    "updated_at",
                ]
            )
        if isinstance(payload, dict):
            return Response(_with_courier_warehouse_aliases(payload, warehouse))
        return Response(payload)
    except ShipdaakIntegrationError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAdminToken])
def shipdaak_sync_warehouse(request, pk: int):
    """
    Sync a local courier warehouse to ShipDaak.

    Registers (or re-registers) the warehouse in ShipDaak using its address
    details and stores the returned pickup/RTO IDs locally.

    Runtime flow is direct-to-Shipdaak. WMS-Backend in this repository is only
    a reference implementation and is not called by Courier_Module.

    Body (optional JSON):
        force (bool): Re-sync even if IDs are already stored locally.
    """
    try:
        warehouse = Warehouse.objects.get(pk=pk)
    except Warehouse.DoesNotExist:
        return Response({"detail": "Courier warehouse not found."}, status=status.HTTP_404_NOT_FOUND)

    force = bool(request.data.get("force", False))

    # Short-circuit: if already synced and force is off, return cached IDs.
    if not force and warehouse.shipdaak_pickup_id and warehouse.shipdaak_rto_id:
        return Response(_with_courier_warehouse_aliases({
            "pickupId": warehouse.shipdaak_pickup_id,
            "rtoId": warehouse.shipdaak_rto_id,
            "synced": True,
            "alreadyExisted": True,
            "syncedAt": (
                warehouse.shipdaak_synced_at.isoformat()
                if warehouse.shipdaak_synced_at else None
            ),
            "warehouseName": warehouse.name,
        }, warehouse))

    client = ShipdaakV2Client()
    try:
        raw = client.create_warehouse(
            warehouse_name=warehouse.name,
            contact_name=warehouse.contact_name,
            contact_no=warehouse.contact_no,
            address=warehouse.address,
            address_2=warehouse.address_2,
            pin_code=str(warehouse.pincode),
            city=warehouse.city,
            state=warehouse.state,
            gst_number=warehouse.gst_number,
        )
        pickup_id, rto_id = _extract_warehouse_ids(raw if isinstance(raw, dict) else {})
        if pickup_id and rto_id:
            warehouse.shipdaak_pickup_id = pickup_id
            warehouse.shipdaak_rto_id = rto_id
            warehouse.shipdaak_synced_at = timezone.now()
            warehouse.save(
                update_fields=[
                    "shipdaak_pickup_id",
                    "shipdaak_rto_id",
                    "shipdaak_synced_at",
                    "updated_at",
                ]
            )
        return Response(_with_courier_warehouse_aliases({
            "pickupId": pickup_id,
            "rtoId": rto_id,
            "synced": bool(pickup_id and rto_id),
            "alreadyExisted": False,
            "warehouseName": warehouse.name,
        }, warehouse))
    except ShipdaakIntegrationError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAdminToken])
def shipdaak_warehouse_status(request, pk: int):
    """
    Return the local ShipDaak sync state of a courier warehouse.

    Reads directly from the local DB (shipdaak_pickup_id, shipdaak_rto_id)
    because direct Shipdaak APIs do not expose status by Courier_Module's local
    warehouse integer ID.
    """
    try:
        warehouse = Warehouse.objects.get(pk=pk)
    except Warehouse.DoesNotExist:
        return Response({"detail": "Courier warehouse not found."}, status=status.HTTP_404_NOT_FOUND)

    synced = bool(warehouse.shipdaak_pickup_id and warehouse.shipdaak_rto_id)
    payload: dict[str, object] = _with_courier_warehouse_aliases(
        {"synced": synced, "warehouseName": warehouse.name},
        warehouse,
    )
    if synced:
        payload["pickupId"] = warehouse.shipdaak_pickup_id
        payload["rtoId"] = warehouse.shipdaak_rto_id
        payload["syncedAt"] = (
            warehouse.shipdaak_synced_at.isoformat()
            if warehouse.shipdaak_synced_at else None
        )
    return Response(payload)


@api_view(["POST"])
@permission_classes([IsAdminToken])
def shipdaak_link_existing_warehouse_id(request, pk: int):
    """
    Manually link a local courier warehouse to an already-existing ShipDaak warehouse ID.

    This is a fallback for accounts/workflows where a "list warehouses" API is
    not exposed and operators already know the ShipDaak warehouse ID.
    """
    try:
        warehouse = Warehouse.objects.get(pk=pk)
    except Warehouse.DoesNotExist:
        return Response({"detail": "Courier warehouse not found."}, status=status.HTTP_404_NOT_FOUND)

    raw_pickup = (
        request.data.get("shipdaak_warehouse_id")
        or request.data.get("shipdaakWarehouseId")
        or request.data.get("warehouse_id")
        or request.data.get("pickup_id")
        or request.data.get("pickupId")
    )
    raw_rto = request.data.get("rto_id") or request.data.get("rtoId") or raw_pickup

    try:
        pickup_id = int(raw_pickup)
        rto_id = int(raw_rto)
    except (TypeError, ValueError):
        return Response(
            {
                "detail": (
                    "shipdaak_warehouse_id (or legacy warehouse_id / pickup_id / pickupId) "
                    "must be a valid integer ShipDaak warehouse ID."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if pickup_id <= 0 or rto_id <= 0:
        return Response(
            {"detail": "ShipDaak warehouse IDs must be positive integers."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    warehouse.shipdaak_pickup_id = pickup_id
    warehouse.shipdaak_rto_id = rto_id
    warehouse.shipdaak_synced_at = timezone.now()
    warehouse.save(
        update_fields=[
            "shipdaak_pickup_id",
            "shipdaak_rto_id",
            "shipdaak_synced_at",
            "updated_at",
        ]
    )

    return Response(
        _with_courier_warehouse_aliases({
            "linked": True,
            "warehouseName": warehouse.name,
            "pickupId": pickup_id,
            "rtoId": rto_id,
            "syncedAt": warehouse.shipdaak_synced_at.isoformat(),
        }, warehouse)
    )


@api_view(["POST"])
@permission_classes([IsAdminToken])
def shipdaak_bulk_import_warehouses(request):
    if not isinstance(request.data, list):
        return Response(
            {"detail": "Request body must be a JSON array of courier warehouses."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    existing_by_name: dict[str, Warehouse] = {}
    for warehouse in Warehouse.objects.all().order_by("id"):
        existing_by_name.setdefault(_normalize_warehouse_name(warehouse.name), warehouse)

    summary = {"created": 0, "updated": 0, "skipped": 0, "failed": []}
    client = ShipdaakV2Client()

    for index, row in enumerate(request.data, start=1):
        normalized, validation_error = _validate_bulk_warehouse_row(row)
        row_name = ""
        if isinstance(row, dict):
            row_name = str(row.get("name", "")).strip()
        if validation_error or normalized is None:
            summary["failed"].append({
                "index": index,
                "name": row_name,
                "error": validation_error or "Invalid row.",
            })
            continue

        key = _normalize_warehouse_name(normalized["name"] or "")
        existing = existing_by_name.get(key)
        if existing:
            summary["skipped"] += 1
            continue

        try:
            payload = client.create_warehouse(
                warehouse_name=normalized["name"] or "",
                contact_name=normalized["contact_name"] or "",
                contact_no=normalized["contact_no"] or "",
                address=normalized["address"] or "",
                address_2=normalized["address_2"],
                pin_code=normalized["pincode"] or "",
                city=normalized["city"] or "",
                state=normalized["state"] or "",
                gst_number=normalized["gst_number"],
            )
            pickup_id, rto_id = _extract_warehouse_ids(payload if isinstance(payload, dict) else {})
            if not pickup_id or not rto_id:
                raise ValueError("ShipDaak response missing pickup/rto warehouse IDs.")

            created = Warehouse.objects.create(
                name=normalized["name"] or "",
                contact_name=normalized["contact_name"] or "",
                contact_no=normalized["contact_no"] or "",
                address=normalized["address"] or "",
                address_2=normalized["address_2"],
                pincode=normalized["pincode"] or "",
                city=normalized["city"] or "",
                state=normalized["state"] or "",
                gst_number=normalized["gst_number"],
                shipdaak_pickup_id=pickup_id,
                shipdaak_rto_id=rto_id,
                shipdaak_synced_at=timezone.now(),
            )
            existing_by_name[key] = created
            summary["created"] += 1
        except (ShipdaakIntegrationError, ValueError, TypeError) as exc:
            summary["failed"].append({
                "index": index,
                "name": normalized["name"],
                "error": str(exc),
            })

    return Response(summary)


# ---------------------------------------------------------------------------
# Rate check / courier discovery
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAdminToken])
def shipdaak_serviceability(request):
    """
    Check courier rates and serviceability for a route.

    Required query params:
        origin      - Source pincode (6 digits)
        destination - Destination pincode (6 digits)
        paymentType - 'cod' or 'prepaid'
        weight      - Package weight in grams
        length      - Package length in cm
        breadth     - Package width in cm
        height      - Package height in cm

    Optional query params:
        filterType  - 'rate' (default) or 'serviceability'
        orderAmount - Order value in INR (required for COD)

    Returns a list sorted by totalCharges (cheapest first).
    Each item's ``id`` is the courierId to pass when booking.
    """
    required = ("origin", "destination", "paymentType", "weight", "length", "breadth", "height")
    missing = [p for p in required if not request.query_params.get(p)]
    if missing:
        return Response(
            {"detail": f"Missing required query parameters: {', '.join(missing)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    params: dict = {
        "filterType": request.query_params.get("filterType", "rate"),
        "origin": request.query_params["origin"],
        "destination": request.query_params["destination"],
        "paymentType": request.query_params["paymentType"],
        "weight": request.query_params["weight"],
        "length": request.query_params["length"],
        "breadth": request.query_params["breadth"],
        "height": request.query_params["height"],
    }
    if order_amount := request.query_params.get("orderAmount"):
        params["orderAmount"] = order_amount

    client = ShipdaakV2Client()
    try:
        return Response(client.serviceability(**params))
    except ShipdaakIntegrationError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAdminToken])
def shipdaak_couriers(request):
    """
    Return all couriers available in the connected ShipDaak account.

    The ``id`` field in each result is the courierId required by:
      - GET /shipdaak/serviceability  (rate check)
      - POST /orders/book-carrier     (booking - pass as carrier_id)
    """
    client = ShipdaakV2Client()
    try:
        return Response(client.get_couriers())
    except ShipdaakIntegrationError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Order lifecycle
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAdminToken])
def shipdaak_track_order(request, pk: int):
    try:
        order = Order.objects.get(pk=pk)
    except Order.DoesNotExist:
        return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

    if not order.awb_number:
        return Response({"detail": "Order has no AWB."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        return Response(ShipdaakLifecycleService.fetch_tracking_for_order(order))
    except ShipdaakIntegrationError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAdminToken])
def shipdaak_cancel_order(request, pk: int):
    try:
        order = Order.objects.get(pk=pk)
    except Order.DoesNotExist:
        return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

    if not order.awb_number:
        return Response({"detail": "Order has no AWB."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        result = ShipdaakLifecycleService.cancel_order_upstream_first(order)
        return Response(
            {
                "status": "success",
                "order_number": order.order_number,
                "previous_status": result["previous_status"],
                "current_status": result["current_status"],
                "upstream_payload": result["upstream_payload"],
            }
        )
    except ShipdaakIntegrationError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAdminToken])
def shipdaak_order_label(request, pk: int):
    try:
        order = Order.objects.get(pk=pk)
    except Order.DoesNotExist:
        return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

    if not order.awb_number:
        return Response({"detail": "Order has no AWB."}, status=status.HTTP_400_BAD_REQUEST)

    client = ShipdaakV2Client()
    try:
        return Response(client.get_label(order.awb_number))
    except ShipdaakIntegrationError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAdminToken])
def shipdaak_manifest(request):
    awb_numbers = request.data.get("awbNumbers") or request.data.get("awb_numbers")
    if not awb_numbers or not isinstance(awb_numbers, list):
        return Response(
            {"detail": "awbNumbers list is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    client = ShipdaakV2Client()
    try:
        return Response(client.generate_manifest(awb_numbers))
    except ShipdaakIntegrationError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAdminToken])
def shipdaak_bulk_label(request):
    awb_numbers = request.data.get("awbNumbers") or request.data.get("awb_numbers")
    if not isinstance(awb_numbers, list) or not awb_numbers:
        return Response(
            {"detail": "awbNumbers list is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    normalized_awbs: list[str] = []
    seen: set[str] = set()
    for value in awb_numbers:
        awb = str(value).strip()
        if not awb:
            continue
        if awb in seen:
            continue
        seen.add(awb)
        normalized_awbs.append(awb)

    if not normalized_awbs:
        return Response(
            {"detail": "awbNumbers must include at least one non-empty AWB."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    limit = _max_bulk_orders()
    if len(normalized_awbs) > limit:
        return Response(
            {
                "detail": f"At most {limit} AWBs can be processed in one request.",
                "code": "batch_limit_exceeded",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    client = ShipdaakV2Client()
    try:
        payload = client.generate_bulk_labels(normalized_awbs, label_format="thermal")
    except ShipdaakIntegrationError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    label_url = _extract_url(payload, ("label_url", "label", "url", "bulk_label_url"))
    if not label_url:
        return Response(
            {"detail": "Shipdaak response did not include a label URL."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response({"label_url": label_url, "awb_count": len(normalized_awbs)})
