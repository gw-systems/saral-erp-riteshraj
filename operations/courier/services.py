import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any

from django.conf import settings
from django.utils import timezone

from .engine import calculate_cost
from .integrations import ShipdaakV2Client
from .integrations.errors import ShipdaakIntegrationError
from .models import Order, OrderStatus, PaymentMode, Courier, Warehouse
from .views.base import load_rates

logger = logging.getLogger('courier')


class BatchRouteValidationError(ValueError):
    """Validation error for multi-order route consistency checks."""

    def __init__(self, message: str, code: str):
        self.code = code
        super().__init__(message)


class BatchRouteValidator:
    """Validate route consistency for batch compare/booking operations."""

    @staticmethod
    def _to_int_pincode(raw_value, field_label: str) -> int:
        try:
            return int(str(raw_value).strip())
        except Exception as exc:
            raise ValueError(f"Invalid {field_label} pincode in selected orders") from exc

    @staticmethod
    def resolve_source_and_destination(
        orders: list[Order],
        warehouse_id: int | None = None,
    ) -> tuple[int, int, Warehouse | None]:
        if not orders:
            raise ValueError("No orders provided")

        selected_warehouse: Warehouse | None = None
        if warehouse_id:
            try:
                selected_warehouse = Warehouse.objects.get(id=warehouse_id)
            except Warehouse.DoesNotExist as exc:
                raise ValueError("Selected courier warehouse not found") from exc

        destination_pincodes = {
            BatchRouteValidator._to_int_pincode(order.recipient_pincode, "destination")
            for order in orders
        }
        if len(destination_pincodes) > 1:
            raise BatchRouteValidationError(
                "All selected orders must have the same destination pincode.",
                code="mixed_destination",
            )
        dest_pincode = destination_pincodes.pop()

        if selected_warehouse:
            source_pincode = BatchRouteValidator._to_int_pincode(
                selected_warehouse.pincode,
                "source",
            )
            return source_pincode, dest_pincode, selected_warehouse

        source_pincodes = {
            BatchRouteValidator._to_int_pincode(order.sender_pincode, "source")
            for order in orders
        }
        if len(source_pincodes) > 1:
            raise BatchRouteValidationError(
                "All selected orders must have the same source pincode unless a courier warehouse override is provided.",
                code="mixed_source",
            )
        source_pincode = source_pincodes.pop()
        return source_pincode, dest_pincode, None


class ShipdaakLivePricingService:
    """Helpers for fetching and normalizing live Shipdaak rates."""

    @staticmethod
    def is_enabled() -> bool:
        return bool(getattr(settings, "SHIPDAAK_LIVE_PRICING_ENABLED", False))

    @staticmethod
    def max_bulk_orders() -> int:
        raw_limit = getattr(settings, "SHIPDAAK_LIVE_BULK_MAX_ORDERS", 50)
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            limit = 50
        return max(limit, 1)

    @staticmethod
    def ensure_batch_size(order_ids: List[int]) -> None:
        limit = ShipdaakLivePricingService.max_bulk_orders()
        if len(order_ids) > limit:
            raise BatchRouteValidationError(
                f"At most {limit} orders can be processed in one live bulk operation.",
                code="batch_limit_exceeded",
            )

    @staticmethod
    def _as_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def extract_courier_id(rate_row: dict[str, Any]) -> int | None:
        raw = (
            rate_row.get("id")
            or rate_row.get("courier_id")
            or rate_row.get("courierId")
        )
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def extract_total_charges(rate_row: dict[str, Any]) -> float | None:
        for key in ("totalCharges", "total_charges", "total_charge", "charges"):
            amount = ShipdaakLivePricingService._as_float(rate_row.get(key))
            if amount is not None:
                return amount
        return None

    @staticmethod
    def extract_mode(rate_row: dict[str, Any]) -> str:
        return str(
            rate_row.get("mode")
            or rate_row.get("service_type")
            or rate_row.get("serviceType")
            or "Surface"
        )

    @staticmethod
    def extract_zone(rate_row: dict[str, Any]) -> str:
        return str(rate_row.get("zone") or rate_row.get("zone_name") or "")

    @staticmethod
    def extract_carrier_name(rate_row: dict[str, Any], courier_id: int) -> str:
        name = (
            rate_row.get("courier_name")
            or rate_row.get("courierName")
            or rate_row.get("name")
            or rate_row.get("courier")
        )
        if name:
            return str(name)
        return f"Shipdaak Courier {courier_id}"

    @staticmethod
    def payment_type(order: Order) -> str:
        return "cod" if str(order.payment_mode or "").strip().lower() == "cod" else "prepaid"

    @staticmethod
    def build_serviceability_params(
        order: Order,
        source_pincode: int,
        dest_pincode: int,
    ) -> dict[str, Any]:
        return {
            "filterType": "rate",
            "origin": str(source_pincode),
            "destination": str(dest_pincode),
            "paymentType": ShipdaakLivePricingService.payment_type(order),
            "weight": int(round(float(order.applicable_weight or order.weight) * 1000)),
            "length": float(order.length),
            "breadth": float(order.width),
            "height": float(order.height),
            "orderAmount": float(order.order_value or 0),
        }

    @staticmethod
    def build_order_items(order: Order) -> list[dict[str, Any]]:
        """
        Build Shipdaak-compatible order_items payload.
        Shipdaak requires at least one item for shipment booking.
        """
        try:
            quantity = int(order.quantity or 1)
        except (TypeError, ValueError):
            quantity = 1
        if quantity < 1:
            quantity = 1

        item_name = (order.item_type or "").strip() or (order.sku or "").strip() or "Item"

        try:
            price = float(order.item_amount or 0)
        except (TypeError, ValueError):
            price = 0.0
        if price <= 0:
            try:
                price = float(order.order_value or 0)
            except (TypeError, ValueError):
                price = 0.0
        if price <= 0:
            price = 1.0

        item: dict[str, Any] = {
            "name": item_name,
            "quantity": quantity,
            "price": price,
        }
        if order.sku:
            item["sku"] = str(order.sku)
        return [item]

    @staticmethod
    def fetch_rates(
        order: Order,
        source_pincode: int,
        dest_pincode: int,
    ) -> list[dict[str, Any]]:
        client = ShipdaakV2Client()
        response = client.serviceability(
            **ShipdaakLivePricingService.build_serviceability_params(
                order=order,
                source_pincode=source_pincode,
                dest_pincode=dest_pincode,
            )
        )
        if not isinstance(response, list):
            return []
        return [row for row in response if isinstance(row, dict)]

    @staticmethod
    def allowed_shipdaak_ids_for_business_type(
        normalized_business_type: str,
    ) -> set[int]:
        if not normalized_business_type:
            return set()
        return set(
            Courier.objects.filter(
                is_active=True,
                carrier_type__iexact=normalized_business_type,
                shipdaak_courier_id__isnull=False,
            ).values_list("shipdaak_courier_id", flat=True)
        )

    @staticmethod
    def normalize_rates(raw_rates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for row in raw_rates:
            courier_id = ShipdaakLivePricingService.extract_courier_id(row)
            total_charges = ShipdaakLivePricingService.extract_total_charges(row)
            if courier_id is None or total_charges is None:
                continue
            pricing = ShipdaakEscalationPolicy.apply(total_charges)

            zone = ShipdaakLivePricingService.extract_zone(row)
            normalized.append(
                {
                    "carrier": ShipdaakLivePricingService.extract_carrier_name(row, courier_id),
                    "carrier_id": courier_id,
                    "mode": ShipdaakLivePricingService.extract_mode(row),
                    "zone": zone,
                    "applied_zone": zone,
                    "total_cost": pricing["customer_total_cost"],
                    "customer_total_cost": pricing["customer_total_cost"],
                    "shipdaak_base_rate": pricing["shipdaak_base_rate"],
                    "escalation_percent": pricing["escalation_percent"],
                    "escalation_amount": pricing["escalation_amount"],
                    "breakdown": {
                        "shipdaak_base_rate": pricing["shipdaak_base_rate"],
                        "escalation_percent": pricing["escalation_percent"],
                        "escalation_amount": pricing["escalation_amount"],
                        "customer_total_cost": pricing["customer_total_cost"],
                    },
                    "service_category": str(
                        row.get("service_category") or row.get("serviceCategory") or ""
                    ),
                    "pricing_source": "shipdaak_live",
                }
            )

        return sorted(normalized, key=lambda x: x["total_cost"])

    @staticmethod
    def find_rate_by_courier(
        raw_rates: list[dict[str, Any]],
        shipdaak_courier_id: int,
    ) -> dict[str, Any] | None:
        for row in raw_rates:
            if ShipdaakLivePricingService.extract_courier_id(row) == shipdaak_courier_id:
                return row
        return None


class ShipdaakEscalationPolicy:
    """Apply customer-facing escalation on top of Shipdaak base rates."""

    DEFAULT_PERCENT = 20.0

    @classmethod
    def escalation_percent(cls) -> float:
        raw = getattr(settings, "SHIPDAAK_UI_ESCALATION_PERCENT", cls.DEFAULT_PERCENT)
        try:
            percent = float(raw)
        except (TypeError, ValueError):
            percent = cls.DEFAULT_PERCENT
        if percent < 0:
            return 0.0
        return round(percent, 2)

    @staticmethod
    def _money(value: Decimal | float | int | str) -> Decimal:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @classmethod
    def apply(cls, shipdaak_base_rate: float) -> dict[str, float]:
        base = cls._money(shipdaak_base_rate)
        percent = Decimal(str(cls.escalation_percent()))
        escalation_amount = cls._money(base * (percent / Decimal("100")))
        customer_total = cls._money(base + escalation_amount)
        return {
            "shipdaak_base_rate": float(base),
            "escalation_percent": float(percent),
            "escalation_amount": float(escalation_amount),
            "customer_total_cost": float(customer_total),
        }


class CarrierService:
    """Service to handle carrier rate comparisons"""

    @staticmethod
    def _source_courier_warehouse_payload(selected_warehouse: Warehouse | None):
        if not selected_warehouse:
            return None
        return {
            "id": selected_warehouse.id,
            "name": selected_warehouse.name,
            "pincode": selected_warehouse.pincode,
            "scope": "courier",
        }

    @staticmethod
    def compare_rates(
        order_ids: List[int],
        business_type: str | None = None,
        warehouse_id: int | None = None,
    ) -> Dict[str, Any]:
        """
        Compare rates for a list of orders across all active couriers.

        Args:
            order_ids (List[int]): List of Order IDs to compare.

        Returns:
            Dict[str, Any]: A dictionary containing:
                - orders: QuerySet of Order objects.
                - carriers: List of dicts with cost details, sorted by total_cost.
                - source_pincode: Verified source pincode.
                - dest_pincode: Verified destination pincode.
                - total_weight: Aggregated weight of all orders.

        Raises:
            ValueError: If orders are missing or invalid.
        """
        orders_qs = Order.objects.filter(id__in=order_ids)
        if orders_qs.count() != len(order_ids):
            raise ValueError("One or more orders not found")
        orders = list(orders_qs)
        if not orders:
            raise ValueError("No orders provided")

        # Aggregate inputs
        total_weight = sum(order.applicable_weight or order.weight for order in orders)

        if ShipdaakLivePricingService.is_enabled():
            ShipdaakLivePricingService.ensure_batch_size(order_ids)
            normalized_business_type = (business_type or "").strip().lower()
            allowed_shipdaak_ids = ShipdaakLivePricingService.allowed_shipdaak_ids_for_business_type(
                normalized_business_type
            )
            selected_warehouse: Warehouse | None = None
            if warehouse_id:
                try:
                    selected_warehouse = Warehouse.objects.get(id=warehouse_id)
                except Warehouse.DoesNotExist as exc:
                    raise ValueError("Selected courier warehouse not found") from exc

            # Preserve existing single-order live behavior and response shape.
            if len(orders) == 1:
                source_pincode, dest_pincode, selected_warehouse = BatchRouteValidator.resolve_source_and_destination(
                    orders=orders,
                    warehouse_id=warehouse_id,
                )
                order = orders[0]
                try:
                    live_rows = ShipdaakLivePricingService.fetch_rates(
                        order=order,
                        source_pincode=source_pincode,
                        dest_pincode=dest_pincode,
                    )
                except ShipdaakIntegrationError as exc:
                    raise ValueError(str(exc)) from exc

                results = ShipdaakLivePricingService.normalize_rates(live_rows)
                if allowed_shipdaak_ids:
                    results = [
                        row for row in results if row["carrier_id"] in allowed_shipdaak_ids
                    ]

                return {
                    "orders": orders,
                    "carriers": results,
                    "source_pincode": source_pincode,
                    "source_warehouse": CarrierService._source_courier_warehouse_payload(selected_warehouse),
                    "source_courier_warehouse": CarrierService._source_courier_warehouse_payload(selected_warehouse),
                    "dest_pincode": dest_pincode,
                    "total_weight": total_weight
                }

            # Bulk live pricing: evaluate each order independently, then aggregate by courier.
            aggregated: dict[int, dict[str, Any]] = {}
            order_ids_set = {order.id for order in orders}
            source_pincodes_seen: set[int] = set()
            destination_pincodes_seen: set[int] = set()

            for order in orders:
                source_pincode = BatchRouteValidator._to_int_pincode(
                    selected_warehouse.pincode if selected_warehouse else order.sender_pincode,
                    "source",
                )
                dest_pincode = BatchRouteValidator._to_int_pincode(order.recipient_pincode, "destination")
                source_pincodes_seen.add(source_pincode)
                destination_pincodes_seen.add(dest_pincode)

                try:
                    live_rows = ShipdaakLivePricingService.fetch_rates(
                        order=order,
                        source_pincode=source_pincode,
                        dest_pincode=dest_pincode,
                    )
                except ShipdaakIntegrationError as exc:
                    logger.warning(
                        "Shipdaak live bulk compare skipped order=%s error=%s",
                        order.order_number,
                        exc,
                    )
                    continue

                for row in live_rows:
                    courier_id = ShipdaakLivePricingService.extract_courier_id(row)
                    if courier_id is None:
                        continue
                    if allowed_shipdaak_ids and courier_id not in allowed_shipdaak_ids:
                        continue

                    total_charges = ShipdaakLivePricingService.extract_total_charges(row)
                    if total_charges is None:
                        continue
                    pricing = ShipdaakEscalationPolicy.apply(total_charges)

                    bucket = aggregated.setdefault(
                        courier_id,
                        {
                            "carrier": ShipdaakLivePricingService.extract_carrier_name(row, courier_id),
                            "carrier_id": courier_id,
                            "applied_zone": "",
                            "pricing_source": "shipdaak_live",
                            "mode_set": set(),
                            "supported_order_ids": set(),
                            "order_quotes": [],
                            "shipdaak_base_rate_total": 0.0,
                            "escalation_amount_total": 0.0,
                            "customer_total_cost": 0.0,
                        },
                    )
                    bucket["mode_set"].add(ShipdaakLivePricingService.extract_mode(row))
                    bucket["supported_order_ids"].add(order.id)
                    bucket["order_quotes"].append(
                        {
                            "order_id": order.id,
                            "order_number": order.order_number,
                            "source_pincode": source_pincode,
                            "dest_pincode": dest_pincode,
                            "shipdaak_base_rate": pricing["shipdaak_base_rate"],
                            "escalation_percent": pricing["escalation_percent"],
                            "escalation_amount": pricing["escalation_amount"],
                            "customer_total_cost": pricing["customer_total_cost"],
                            "total_cost": pricing["customer_total_cost"],
                        }
                    )
                    bucket["shipdaak_base_rate_total"] += pricing["shipdaak_base_rate"]
                    bucket["escalation_amount_total"] += pricing["escalation_amount"]
                    bucket["customer_total_cost"] += pricing["customer_total_cost"]

            results: list[dict[str, Any]] = []
            total_orders = len(orders)
            for courier_id, bucket in aggregated.items():
                supported_ids = set(bucket["supported_order_ids"])
                unsupported_ids = sorted(order_ids_set - supported_ids)
                supported_count = len(supported_ids)
                unsupported_count = len(unsupported_ids)
                coverage_percent = round(
                    (supported_count / total_orders) * 100 if total_orders else 0.0,
                    2,
                )
                mode_value = (
                    next(iter(bucket["mode_set"]))
                    if len(bucket["mode_set"]) == 1
                    else "Mixed"
                )
                results.append(
                    {
                        "carrier": bucket["carrier"],
                        "carrier_id": courier_id,
                        "mode": mode_value,
                        "applied_zone": bucket["applied_zone"],
                        "pricing_source": "shipdaak_live",
                        "total_orders": total_orders,
                        "supported_orders_count": supported_count,
                        "unsupported_orders_count": unsupported_count,
                        "unsupported_order_ids": unsupported_ids,
                        "coverage_percent": coverage_percent,
                        "shipdaak_base_rate_total": round(bucket["shipdaak_base_rate_total"], 2),
                        "escalation_amount_total": round(bucket["escalation_amount_total"], 2),
                        "customer_total_cost": round(bucket["customer_total_cost"], 2),
                        "total_cost": round(bucket["customer_total_cost"], 2),
                        "order_quotes": sorted(
                            bucket["order_quotes"],
                            key=lambda row: (row["order_number"], row["order_id"]),
                        ),
                    }
                )

            logger.info(
                "Shipdaak live bulk compare completed orders=%s carriers=%s warehouse_override=%s",
                len(orders),
                len(results),
                bool(selected_warehouse),
            )

            results.sort(key=lambda row: (-row["supported_orders_count"], row["total_cost"]))

            source_pincode = (
                BatchRouteValidator._to_int_pincode(selected_warehouse.pincode, "source")
                if selected_warehouse
                else (
                    next(iter(source_pincodes_seen))
                    if len(source_pincodes_seen) == 1
                    else None
                )
            )
            dest_pincode = (
                next(iter(destination_pincodes_seen))
                if len(destination_pincodes_seen) == 1
                else None
            )

            return {
                "orders": orders,
                "carriers": results,
                "source_pincode": source_pincode,
                "source_warehouse": CarrierService._source_courier_warehouse_payload(selected_warehouse),
                "source_courier_warehouse": CarrierService._source_courier_warehouse_payload(selected_warehouse),
                "dest_pincode": dest_pincode,
                "total_weight": total_weight
            }

        source_pincode, dest_pincode, selected_warehouse = BatchRouteValidator.resolve_source_and_destination(
            orders=orders,
            warehouse_id=warehouse_id,
        )

        is_cod = any(order.payment_mode == PaymentMode.COD for order in orders)
        total_order_value = sum(
            order.order_value for order in orders
            if order.payment_mode == PaymentMode.COD
        )

        rates = load_rates()
        results = []

        normalized_business_type = (business_type or "").strip().lower()

        for carrier in rates:
            if not carrier.get("active", True):
                continue

            if normalized_business_type:
                carrier_type = str(carrier.get("type", "")).strip().lower()
                if carrier_type and carrier_type != normalized_business_type:
                    continue

            try:
                res = calculate_cost(
                    weight=total_weight,
                    source_pincode=source_pincode,
                    dest_pincode=dest_pincode,
                    carrier_data=carrier,
                    is_cod=is_cod,
                    order_value=total_order_value
                )

                if res.get("serviceable") is False:
                    continue

                res["mode"] = carrier.get("mode", "Surface")
                res["applied_zone"] = res.get("zone", "")
                res["carrier_id"] = carrier.get("id")
                res["order_count"] = len(order_ids)
                res["total_weight"] = total_weight
                results.append(res)

            except Exception as e:
                logger.warning(f"Carrier {carrier.get('carrier_name')} failed: {e}")
                continue

        return {
            "orders": orders,
            "carriers": sorted(results, key=lambda x: x["total_cost"]),
            "source_pincode": source_pincode,
            "source_warehouse": CarrierService._source_courier_warehouse_payload(selected_warehouse),
            "source_courier_warehouse": CarrierService._source_courier_warehouse_payload(selected_warehouse),
            "dest_pincode": dest_pincode,
            "total_weight": total_weight
        }


class ShipdaakWarehouseService:
    """Shared helpers for linking or creating ShipDaak warehouse mappings safely."""

    @staticmethod
    def extract_warehouse_ids(payload: dict[str, Any]) -> tuple[int | None, int | None]:
        pickup_id = payload.get("pickupId")
        rto_id = payload.get("rtoId")
        if pickup_id and rto_id:
            return pickup_id, rto_id

        nested = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        return nested.get("pickup_warehouse_id"), nested.get("rto_warehouse_id")

    @staticmethod
    def parse_force_flag(raw_value: Any) -> bool:
        if isinstance(raw_value, bool):
            return raw_value
        if raw_value is None:
            return False
        normalized = str(raw_value).strip().lower()
        return normalized in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _save_linked_ids(
        warehouse: Warehouse,
        pickup_id: int,
        rto_id: int,
    ) -> dict[str, Any]:
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
        return {
            "pickupId": pickup_id,
            "rtoId": rto_id,
            "synced": True,
            "alreadyExisted": False,
            "warehouseName": warehouse.name,
            "syncedAt": (
                warehouse.shipdaak_synced_at.isoformat()
                if warehouse.shipdaak_synced_at else None
            ),
        }

    @classmethod
    def link_existing_ids(
        cls,
        warehouse: Warehouse,
        pickup_id: int,
        rto_id: int | None = None,
    ) -> dict[str, Any]:
        resolved_rto_id = rto_id if rto_id is not None else pickup_id
        return cls._save_linked_ids(
            warehouse=warehouse,
            pickup_id=int(pickup_id),
            rto_id=int(resolved_rto_id),
        )

    @classmethod
    def ensure_shipdaak_link(
        cls,
        warehouse: Warehouse,
        *,
        force: bool = False,
        client: ShipdaakV2Client | None = None,
    ) -> dict[str, Any]:
        if not force and warehouse.shipdaak_pickup_id and warehouse.shipdaak_rto_id:
            return {
                "pickupId": warehouse.shipdaak_pickup_id,
                "rtoId": warehouse.shipdaak_rto_id,
                "synced": True,
                "alreadyExisted": True,
                "warehouseName": warehouse.name,
                "syncedAt": (
                    warehouse.shipdaak_synced_at.isoformat()
                    if warehouse.shipdaak_synced_at else None
                ),
            }

        active_client = client or ShipdaakV2Client()
        payload = active_client.create_warehouse(
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
        pickup_id, rto_id = cls.extract_warehouse_ids(payload if isinstance(payload, dict) else {})
        if not pickup_id or not rto_id:
            return {
                "pickupId": pickup_id,
                "rtoId": rto_id,
                "synced": False,
                "alreadyExisted": False,
                "warehouseName": warehouse.name,
                "syncedAt": (
                    warehouse.shipdaak_synced_at.isoformat()
                    if warehouse.shipdaak_synced_at else None
                ),
            }
        return cls._save_linked_ids(
            warehouse=warehouse,
            pickup_id=int(pickup_id),
            rto_id=int(rto_id),
        )


class ShipdaakLifecycleService:
    """Shared lifecycle operations for Shipdaak-backed shipments."""

    ACTIVE_SYNC_STATUSES = (
        OrderStatus.BOOKED,
        OrderStatus.MANIFESTED,
        OrderStatus.PICKED_UP,
        OrderStatus.OUT_FOR_DELIVERY,
    )
    TERMINAL_STATUSES = {
        OrderStatus.DELIVERED,
        OrderStatus.CANCELLED,
        OrderStatus.NDR,
        OrderStatus.RTO,
    }
    _STATUS_RANK = {
        OrderStatus.DRAFT: 0,
        OrderStatus.BOOKED: 10,
        OrderStatus.MANIFESTED: 20,
        OrderStatus.PICKED_UP: 30,
        OrderStatus.OUT_FOR_DELIVERY: 40,
        OrderStatus.NDR: 45,
        OrderStatus.DELIVERED: 50,
        OrderStatus.RTO: 50,
        OrderStatus.CANCELLED: 50,
    }
    _TRACKING_STATUS_KEYS = (
        "current_status",
        "shipment_status",
        "tracking_status",
        "latest_status",
        "order_status",
        "status",
        "state",
    )
    _TRACKING_EVENT_KEYS = (
        "events",
        "event_list",
        "tracking",
        "tracking_data",
        "history",
        "activities",
        "shipment_track_activities",
    )

    @staticmethod
    def _normalize_status_token(value: str | None) -> str:
        token = str(value or "").strip().lower()
        if not token:
            return ""
        for separator in ("-", " ", "/", "."):
            token = token.replace(separator, "_")
        while "__" in token:
            token = token.replace("__", "_")
        return token.strip("_")

    @classmethod
    def _extract_status_from_list(cls, items: list[Any]) -> str | None:
        for item in reversed(items):
            status = cls._extract_upstream_status(item)
            if status:
                return status
        return None

    @classmethod
    def _extract_upstream_status(cls, payload: Any) -> str | None:
        if isinstance(payload, str):
            text = payload.strip()
            return text or None

        if isinstance(payload, list):
            return cls._extract_status_from_list(payload)

        if not isinstance(payload, dict):
            return None

        for key in cls._TRACKING_STATUS_KEYS:
            if key not in payload:
                continue
            raw_value = payload.get(key)
            if isinstance(raw_value, str) and raw_value.strip():
                return raw_value.strip()
            if isinstance(raw_value, (dict, list)):
                nested = cls._extract_upstream_status(raw_value)
                if nested:
                    return nested

        for key in cls._TRACKING_EVENT_KEYS:
            raw_events = payload.get(key)
            if isinstance(raw_events, list):
                nested = cls._extract_status_from_list(raw_events)
                if nested:
                    return nested
            elif isinstance(raw_events, dict):
                nested = cls._extract_upstream_status(raw_events)
                if nested:
                    return nested

        for key, value in payload.items():
            if isinstance(value, str) and "status" in str(key).lower() and value.strip():
                return value.strip()

        for value in payload.values():
            if isinstance(value, (dict, list)):
                nested = cls._extract_upstream_status(value)
                if nested:
                    return nested
        return None

    @classmethod
    def map_upstream_status(cls, upstream_status: str | None) -> str | None:
        token = cls._normalize_status_token(upstream_status)
        if not token:
            return None

        if token in {"pickup_scheduled", "pickup_schedule", "manifested"}:
            return OrderStatus.MANIFESTED
        if token in {"in_transit", "picked_up", "pickup_complete"}:
            return OrderStatus.PICKED_UP
        if token == "out_for_delivery":
            return OrderStatus.OUT_FOR_DELIVERY
        if token == "delivered":
            return OrderStatus.DELIVERED
        if token in {"ndr", "non_delivery_report", "non_delivery"}:
            return OrderStatus.NDR
        if token in {"rto", "rto_in_transit", "rto_delivered"} or token.startswith("rto_"):
            return OrderStatus.RTO
        if "cancel" in token:
            return OrderStatus.CANCELLED
        return None

    @classmethod
    def extract_mapped_status(cls, tracking_payload: Any) -> tuple[str | None, str | None]:
        upstream_status = cls._extract_upstream_status(tracking_payload)
        return upstream_status, cls.map_upstream_status(upstream_status)

    @staticmethod
    def fetch_tracking_by_awb(awb_number: str) -> Any:
        client = ShipdaakV2Client()
        return client.track_shipment(awb_number)

    @classmethod
    def fetch_tracking_for_order(cls, order: Order) -> Any:
        if not order.awb_number:
            raise ValueError("Order has no AWB.")
        return cls.fetch_tracking_by_awb(order.awb_number)

    @classmethod
    def _should_apply_transition(cls, current_status: str, mapped_status: str | None) -> bool:
        if not mapped_status:
            return False
        if current_status == mapped_status:
            return False
        if current_status in cls.TERMINAL_STATUSES:
            return False

        current_rank = cls._STATUS_RANK.get(current_status, 0)
        mapped_rank = cls._STATUS_RANK.get(mapped_status, 0)
        if mapped_rank < current_rank:
            return False
        return True

    @classmethod
    def apply_mapped_status(cls, order: Order, mapped_status: str | None) -> dict[str, Any]:
        previous_status = order.status
        if not cls._should_apply_transition(previous_status, mapped_status):
            return {
                "updated": False,
                "previous_status": previous_status,
                "current_status": order.status,
            }

        order.status = mapped_status
        order.save(update_fields=["status", "updated_at"])
        return {
            "updated": True,
            "previous_status": previous_status,
            "current_status": order.status,
        }

    @classmethod
    def sync_order_status(cls, order: Order) -> dict[str, Any]:
        tracking_payload = cls.fetch_tracking_for_order(order)
        upstream_status, mapped_status = cls.extract_mapped_status(tracking_payload)
        update_result = cls.apply_mapped_status(order, mapped_status)
        return {
            "tracking_payload": tracking_payload,
            "upstream_status": upstream_status,
            "mapped_status": mapped_status,
            "status_updated": update_result["updated"],
            "previous_status": update_result["previous_status"],
            "current_status": update_result["current_status"],
        }

    @classmethod
    def cancel_order_upstream_first(cls, order: Order) -> dict[str, Any]:
        upstream_payload = None
        upstream_called = False
        if order.awb_number:
            client = ShipdaakV2Client()
            upstream_payload = client.cancel_shipment(order.awb_number)
            upstream_called = True

        update_result = cls.apply_mapped_status(order, OrderStatus.CANCELLED)
        return {
            "upstream_payload": upstream_payload,
            "upstream_called": upstream_called,
            "status_updated": update_result["updated"],
            "previous_status": update_result["previous_status"],
            "current_status": update_result["current_status"],
        }


class BookingService:
    """Service to handle booking operations"""

    @staticmethod
    def _normalize_carrier_label(value: str | None) -> str:
        label = (value or "").strip().lower()
        label = label.replace(" - surface - ", " - ")
        label = " ".join(label.split())
        return label

    @staticmethod
    def _resolve_carrier_data(
        rates: List[Dict[str, Any]],
        carrier_id: int | None = None,
        carrier_name: str | None = None,
        mode: str | None = None,
    ) -> Dict[str, Any] | None:
        if carrier_id:
            for carrier in rates:
                if carrier.get("id") == carrier_id:
                    return carrier
            return None

        expected_name = BookingService._normalize_carrier_label(carrier_name)
        expected_mode = (mode or "").strip().lower()
        for carrier in rates:
            candidate_name = BookingService._normalize_carrier_label(carrier.get("carrier_name"))
            candidate_mode = str(carrier.get("mode", "")).strip().lower()
            if candidate_name == expected_name and (not expected_mode or candidate_mode == expected_mode):
                return carrier
        return None

    @staticmethod
    def _resolve_courier_object(carrier_data: Dict[str, Any]) -> Courier:
        if carrier_data.get("id"):
            try:
                return Courier.objects.get(id=carrier_data["id"])
            except Courier.DoesNotExist:
                pass

        db_name = carrier_data.get("original_name") or carrier_data.get("carrier_name")
        try:
            return Courier.objects.get(name=db_name)
        except Courier.DoesNotExist as exc:
            raise ValueError(f"Carrier object {db_name} not found in DB") from exc

    @staticmethod
    def _ensure_warehouse_synced(order: Order) -> None:
        """Assert that the order's warehouse has ShipDaak pickup/RTO IDs.

        Reads the local DB fields (shipdaak_pickup_id / shipdaak_rto_id) that are
        populated by the warehouse sync endpoint. We intentionally read local
        fields directly because direct Shipdaak APIs do not provide a status
        lookup by Courier_Module warehouse integer ID.
        """
        if not order.warehouse:
            raise ValueError(f"Order {order.order_number} is missing a courier warehouse.")

        warehouse = order.warehouse
        if warehouse.shipdaak_pickup_id and warehouse.shipdaak_rto_id:
            return

        raise ValueError(
            f"Courier warehouse '{warehouse.name}' is not synced to Shipdaak. "
            f"Call POST /shipdaak/warehouses/{warehouse.id}/sync first."
        )

    
    @staticmethod
    def book_orders(
        order_ids: List[int],
        carrier_name: str | None = None,
        mode: str | None = None,
        carrier_id: int | None = None,
        business_type: str | None = None,
        use_global_account: bool = False,
        warehouse_id: int | None = None,
    ) -> Dict[str, Any]:
        """
        Book a list of orders with a specific carrier.

        Args:
            order_ids (List[int]): List of Order IDs to book.
            carrier_name (str): Name of the carrier (referenced in Courier model).
            mode (str): Transport mode (e.g., 'Surface', 'Air').

        Returns:
            Dict[str, Any]: Booking result details including status and cost.

        Raises:
            ValueError: If carrier not found, route not serviceable, or orders invalid.
        """
        orders_qs = Order.objects.filter(id__in=order_ids).select_related("warehouse", "carrier")
        if orders_qs.count() != len(order_ids):
             raise ValueError("One or more orders not found")
        orders = list(orders_qs)
        if not orders:
            raise ValueError("No orders provided")

        live_pricing_enabled = ShipdaakLivePricingService.is_enabled()
        selected_warehouse: Warehouse | None = None
        if warehouse_id:
            try:
                selected_warehouse = Warehouse.objects.get(id=warehouse_id)
            except Warehouse.DoesNotExist as exc:
                raise ValueError("Selected courier warehouse not found") from exc

        if live_pricing_enabled:
            ShipdaakLivePricingService.ensure_batch_size(order_ids)
            if not getattr(settings, "SHIPDAAK_ENABLE_BOOKING", False):
                raise ValueError(
                    "SHIPDAAK_ENABLE_BOOKING must be enabled when SHIPDAAK_LIVE_PRICING_ENABLED is true."
                )

            if carrier_id is None:
                raise ValueError("carrier_id is required in live pricing mode.")

            selected_token = int(carrier_id)
            selected_shipdaak_courier_id = selected_token

            courier_obj = Courier.objects.filter(
                shipdaak_courier_id=selected_shipdaak_courier_id,
                is_active=True,
            ).first()
            if not courier_obj:
                fallback_local = Courier.objects.filter(id=selected_token, is_active=True).first()
                if fallback_local and fallback_local.shipdaak_courier_id:
                    courier_obj = fallback_local
                    selected_shipdaak_courier_id = int(fallback_local.shipdaak_courier_id)

            if not courier_obj:
                raise ValueError(
                    f"No active courier mapping found for Shipdaak courier ID {carrier_id}."
                )

            normalized_business_type = (business_type or "").strip().lower()
            if normalized_business_type:
                courier_type = (courier_obj.carrier_type or "").strip().lower()
                if courier_type and courier_type != normalized_business_type:
                    raise ValueError(
                        f"Selected carrier type '{courier_obj.carrier_type}' does not match requested "
                        f"business_type '{normalized_business_type}'."
                    )

            client: ShipdaakV2Client | None = None
            updated_numbers: list[str] = []
            failures: list[dict[str, Any]] = []
            booked_order_quotes: list[dict[str, Any]] = []
            mode_set: set[str] = set()
            total_customer_cost = 0.0
            total_base_rate = 0.0
            total_escalation = 0.0
            last_pricing: dict[str, float] | None = None

            for order in orders:
                if order.status != OrderStatus.DRAFT:
                    failures.append(
                        {
                            "order_id": order.id,
                            "order_number": order.order_number,
                            "code": "invalid_status",
                            "error": f"Only DRAFT orders can be booked. Current status: {order.status}",
                        }
                    )
                    continue

                if selected_warehouse:
                    order.warehouse = selected_warehouse

                if not order.warehouse:
                    failures.append(
                        {
                            "order_id": order.id,
                            "order_number": order.order_number,
                            "code": "missing_warehouse",
                            "error": "courier warehouse is required for Shipdaak booking.",
                        }
                    )
                    continue

                try:
                    BookingService._ensure_warehouse_synced(order)
                except ValueError as exc:
                    failures.append(
                        {
                            "order_id": order.id,
                            "order_number": order.order_number,
                            "code": "warehouse_not_synced",
                            "error": str(exc),
                        }
                    )
                    continue

                source_pincode = BatchRouteValidator._to_int_pincode(
                    selected_warehouse.pincode if selected_warehouse else order.sender_pincode,
                    "source",
                )
                dest_pincode = BatchRouteValidator._to_int_pincode(
                    order.recipient_pincode,
                    "destination",
                )

                try:
                    live_rows = ShipdaakLivePricingService.fetch_rates(
                        order=order,
                        source_pincode=source_pincode,
                        dest_pincode=dest_pincode,
                    )
                except ShipdaakIntegrationError as exc:
                    failures.append(
                        {
                            "order_id": order.id,
                            "order_number": order.order_number,
                            "code": "rate_fetch_failed",
                            "error": str(exc),
                        }
                    )
                    continue

                selected_rate = ShipdaakLivePricingService.find_rate_by_courier(
                    raw_rates=live_rows,
                    shipdaak_courier_id=selected_shipdaak_courier_id,
                )
                if not selected_rate:
                    failures.append(
                        {
                            "order_id": order.id,
                            "order_number": order.order_number,
                            "code": "not_serviceable",
                            "error": "Selected courier is not serviceable for this order.",
                        }
                    )
                    continue

                live_total_cost = ShipdaakLivePricingService.extract_total_charges(selected_rate)
                if live_total_cost is None:
                    failures.append(
                        {
                            "order_id": order.id,
                            "order_number": order.order_number,
                            "code": "missing_rate",
                            "error": "Live Shipdaak rate is missing total charges.",
                        }
                    )
                    continue
                pricing = ShipdaakEscalationPolicy.apply(live_total_cost)
                last_pricing = pricing

                shipdaak_order_ref = str(order.external_order_id or order.order_number).strip()
                if not shipdaak_order_ref:
                    failures.append(
                        {
                            "order_id": order.id,
                            "order_number": order.order_number,
                            "code": "missing_order_reference",
                            "error": "Order reference cannot be empty for Shipdaak booking.",
                        }
                    )
                    continue

                try:
                    if client is None:
                        client = ShipdaakV2Client()
                    shipment_payload = client.create_shipment(
                        order_id=shipdaak_order_ref,
                        courier_id=int(selected_shipdaak_courier_id),
                        weight_kg=float(order.applicable_weight or order.weight),
                        length_cm=float(order.length),
                        breadth_cm=float(order.width),
                        height_cm=float(order.height),
                        pickup_warehouse_id=int(order.warehouse.shipdaak_pickup_id),
                        rto_warehouse_id=int(order.warehouse.shipdaak_rto_id),
                        pay_type=ShipdaakLivePricingService.payment_type(order),
                        total_amount=float(order.order_value or 0),
                        recipient_name=order.recipient_name,
                        recipient_address=order.recipient_address,
                        recipient_pincode=str(order.recipient_pincode),
                        recipient_phone=order.recipient_contact,
                        recipient_city=order.recipient_city or "",
                        recipient_state=order.recipient_state or "",
                        order_items=ShipdaakLivePricingService.build_order_items(order),
                        use_global_account=bool(use_global_account),
                    )
                except ShipdaakIntegrationError as exc:
                    failures.append(
                        {
                            "order_id": order.id,
                            "order_number": order.order_number,
                            "code": "upstream_booking_failed",
                            "error": str(exc),
                        }
                    )
                    continue

                awb = shipment_payload.get("awb_number")
                if not awb:
                    failures.append(
                        {
                            "order_id": order.id,
                            "order_number": order.order_number,
                            "code": "missing_awb",
                            "error": "Upstream booking did not return awb_number.",
                        }
                    )
                    continue

                mode_value = ShipdaakLivePricingService.extract_mode(selected_rate)
                mode_set.add(mode_value)

                order.carrier = courier_obj
                order.mode = mode_value
                order.zone_applied = ShipdaakLivePricingService.extract_zone(selected_rate)
                order.total_cost = pricing["customer_total_cost"]
                order.cost_breakdown = {
                    "pricing_source": "shipdaak_live",
                    "shipdaak_base_rate": pricing["shipdaak_base_rate"],
                    "escalation_percent": pricing["escalation_percent"],
                    "escalation_amount": pricing["escalation_amount"],
                    "customer_total_cost": pricing["customer_total_cost"],
                    "shipdaak_courier_id": selected_shipdaak_courier_id,
                }
                order.awb_number = awb
                order.shipdaak_shipment_id = str(
                    shipment_payload.get("shipment_id") or shipment_payload.get("order_id") or ""
                ) or None
                order.shipdaak_label_url = shipment_payload.get("label")
                order.status = OrderStatus.BOOKED
                order.booked_at = timezone.now()
                order.save()

                updated_numbers.append(order.order_number)
                booked_order_quotes.append(
                    {
                        "order_id": order.id,
                        "order_number": order.order_number,
                        "shipdaak_base_rate": pricing["shipdaak_base_rate"],
                        "escalation_percent": pricing["escalation_percent"],
                        "escalation_amount": pricing["escalation_amount"],
                        "customer_total_cost": pricing["customer_total_cost"],
                        "total_cost": pricing["customer_total_cost"],
                    }
                )
                total_customer_cost += pricing["customer_total_cost"]
                total_base_rate += pricing["shipdaak_base_rate"]
                total_escalation += pricing["escalation_amount"]

            if updated_numbers and failures:
                status_text = "partial_success"
                message = (
                    f"{len(updated_numbers)} order(s) booked with {courier_obj.name}; "
                    f"{len(failures)} failed."
                )
            elif updated_numbers:
                status_text = "success"
                message = f"{len(updated_numbers)} order(s) booked with {courier_obj.name}"
            else:
                status_text = "failed"
                message = "No orders were booked."

            coverage_percent = round(
                (len(updated_numbers) / len(orders)) * 100 if orders else 0.0,
                2,
            )
            mode_value = (
                next(iter(mode_set))
                if len(mode_set) == 1
                else ("Mixed" if mode_set else (mode or "Surface"))
            )

            failure_code_counts: dict[str, int] = {}
            for failure in failures:
                code = str(failure.get("code") or "unknown")
                failure_code_counts[code] = failure_code_counts.get(code, 0) + 1

            logger.info(
                "Shipdaak live bulk booking completed requested=%s booked=%s failed=%s codes=%s",
                len(orders),
                len(updated_numbers),
                len(failures),
                failure_code_counts,
            )

            response: dict[str, Any] = {
                "status": status_text,
                "message": message,
                "orders_updated": updated_numbers,
                "failures": failures,
                "total_orders": len(orders),
                "supported_orders_count": len(updated_numbers),
                "unsupported_orders_count": len(failures),
                "coverage_percent": coverage_percent,
                "total_cost": round(total_customer_cost, 2),
                "customer_total_cost": round(total_customer_cost, 2),
                "shipdaak_base_rate_total": round(total_base_rate, 2),
                "escalation_amount_total": round(total_escalation, 2),
                "carrier": courier_obj.name,
                "mode": mode_value,
                "booking_mode": "shipdaak_v2_live_pricing",
                "order_quotes": booked_order_quotes,
            }
            if len(updated_numbers) == 1 and not failures and last_pricing is not None:
                response["shipdaak_base_rate"] = last_pricing["shipdaak_base_rate"]
                response["escalation_percent"] = last_pricing["escalation_percent"]
                response["escalation_amount"] = last_pricing["escalation_amount"]
            return response

        total_weight = sum(order.applicable_weight or order.weight for order in orders)
        source_pincode, dest_pincode, selected_warehouse = BatchRouteValidator.resolve_source_and_destination(
            orders=orders,
            warehouse_id=warehouse_id,
        )

        is_cod = any(order.payment_mode == PaymentMode.COD for order in orders)
        total_order_value = sum(
            order.order_value for order in orders
            if order.payment_mode == PaymentMode.COD
        )

        # Find Carrier
        rates = load_rates()
        carrier_data = BookingService._resolve_carrier_data(
            rates=rates,
            carrier_id=carrier_id,
            carrier_name=carrier_name,
            mode=mode,
        )
        
        if not carrier_data:
            raise ValueError("Carrier not found")

        if not mode:
            mode = carrier_data.get("mode")

        # Re-Calculate
        cost_result = calculate_cost(
            weight=total_weight,
            source_pincode=source_pincode,
            dest_pincode=dest_pincode,
            carrier_data=carrier_data,
            is_cod=is_cod,
            order_value=total_order_value
        )

        if cost_result.get("serviceable") is False:
             raise ValueError(f"Route not serviceable by {carrier_data.get('carrier_name')}")
             
        # Get Courier DB Object
        courier_obj = BookingService._resolve_courier_object(carrier_data)

        normalized_business_type = (business_type or "").strip().lower()
        if normalized_business_type:
            courier_type = (courier_obj.carrier_type or "").strip().lower()
            if courier_type and courier_type != normalized_business_type:
                raise ValueError(
                    f"Selected carrier type '{courier_obj.carrier_type}' does not match requested "
                    f"business_type '{normalized_business_type}'."
                )

        # Legacy local booking flow stays available behind feature flag
        if not getattr(settings, "SHIPDAAK_ENABLE_BOOKING", False):
            updated_numbers = []
            for order in orders:
                order.carrier = courier_obj
                order.mode = mode
                order.zone_applied = cost_result.get("zone", "")
                order.total_cost = cost_result["total_cost"]
                order.cost_breakdown = cost_result.get("breakdown", {})
                order.status = OrderStatus.BOOKED
                order.booked_at = timezone.now()
                order.save()
                updated_numbers.append(order.order_number)

            return {
                "status": "success",
                "message": f"{len(orders)} order(s) booked with {carrier_data.get('carrier_name')}",
                "orders_updated": updated_numbers,
                "total_cost": cost_result["total_cost"],
                "carrier": carrier_data.get("carrier_name"),
                "mode": mode,
                "booking_mode": "local",
            }

        # Shipdaak v2 booking path
        client: ShipdaakV2Client | None = None
        updated_numbers: list[str] = []
        failures: list[dict[str, Any]] = []

        resolved_shipdaak_courier_id = courier_obj.shipdaak_courier_id or carrier_data.get("id")
        if not resolved_shipdaak_courier_id:
            raise ValueError(
                f"Carrier '{courier_obj.name}' has no Shipdaak courier ID mapping."
            )

        for order in orders:
            if selected_warehouse:
                order.warehouse = selected_warehouse

            if not order.warehouse:
                failures.append(
                    {
                        "order_id": order.id,
                        "order_number": order.order_number,
                        "error": "courier warehouse is required for Shipdaak booking.",
                    }
                )
                continue

            try:
                if client is None:
                    client = ShipdaakV2Client()
                BookingService._ensure_warehouse_synced(order)
                shipdaak_order_ref = order.external_order_id or order.order_number
                shipment_payload = client.create_shipment(
                    order_id=shipdaak_order_ref,
                    courier_id=int(resolved_shipdaak_courier_id),
                    weight_kg=float(order.applicable_weight or order.weight),
                    length_cm=float(order.length),
                    breadth_cm=float(order.width),
                    height_cm=float(order.height),
                    pickup_warehouse_id=int(order.warehouse.shipdaak_pickup_id),
                    rto_warehouse_id=int(order.warehouse.shipdaak_rto_id),
                    pay_type=(
                        "cod"
                        if str(order.payment_mode or "").strip().lower() == "cod"
                        else "prepaid"
                    ),
                    total_amount=float(order.order_value or 0),
                    recipient_name=order.recipient_name,
                    recipient_address=order.recipient_address,
                    recipient_pincode=str(order.recipient_pincode),
                    recipient_phone=order.recipient_contact,
                    recipient_city=order.recipient_city or "",
                    recipient_state=order.recipient_state or "",
                    order_items=ShipdaakLivePricingService.build_order_items(order),
                    use_global_account=bool(use_global_account),
                )
                awb = shipment_payload.get("awb_number")
                if not awb:
                    raise ValueError("Upstream booking did not return awb_number.")

                order.carrier = courier_obj
                order.mode = mode
                order.zone_applied = cost_result.get("zone", "")
                order.total_cost = cost_result["total_cost"]
                order.cost_breakdown = cost_result.get("breakdown", {})
                order.awb_number = awb
                order.shipdaak_shipment_id = str(
                    shipment_payload.get("shipment_id") or shipment_payload.get("order_id") or ""
                ) or None
                order.shipdaak_label_url = shipment_payload.get("label")
                order.status = OrderStatus.BOOKED
                order.booked_at = timezone.now()
                order.save()
                updated_numbers.append(order.order_number)
            except (ShipdaakIntegrationError, ValueError) as exc:
                failures.append(
                    {
                        "order_id": order.id,
                        "order_number": order.order_number,
                        "error": str(exc),
                    }
                )

        if updated_numbers and failures:
            status_text = "partial_success"
            message = (
                f"{len(updated_numbers)} order(s) booked with {carrier_data.get('carrier_name')}; "
                f"{len(failures)} failed."
            )
        elif updated_numbers:
            status_text = "success"
            message = f"{len(updated_numbers)} order(s) booked with {carrier_data.get('carrier_name')}"
        else:
            status_text = "failed"
            message = "No orders were booked."

        return {
            "status": status_text,
            "message": message,
            "orders_updated": updated_numbers,
            "failures": failures,
            "total_orders": len(orders),
            "supported_orders_count": len(updated_numbers),
            "unsupported_orders_count": len(failures),
            "coverage_percent": round((len(updated_numbers) / len(orders)) * 100 if orders else 0.0, 2),
            "total_cost": cost_result["total_cost"],
            "carrier": carrier_data.get("carrier_name"),
            "mode": mode,
            "booking_mode": "shipdaak_v2",
        }
