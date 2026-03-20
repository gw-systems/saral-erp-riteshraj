"""
Order Management Views.
Contains OrderViewSet for CRUD operations on orders.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.conf import settings
from django.utils import timezone

from ..integrations.errors import ShipdaakIntegrationError
from ..models import Order, OrderStatus, PaymentMode, Courier
from ..permissions import IsAdminToken
from ..serializers import (
    OrderSerializer, OrderUpdateSerializer, CarrierSelectionSerializer
)
from ..engine import calculate_cost
from .base import load_rates, generate_order_number
from ..services import (
    CarrierService,
    BookingService,
    BatchRouteValidationError,
    ShipdaakLifecycleService,
)


def _extract_warehouse_ids(payload: dict) -> tuple[int | None, int | None]:
    pickup_id = payload.get("pickupId")
    rto_id = payload.get("rtoId")
    if pickup_id and rto_id:
        return pickup_id, rto_id

    nested = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return nested.get("pickup_warehouse_id"), nested.get("rto_warehouse_id")


def _build_shipdaak_order_items(order: Order) -> list[dict]:
    """
    Build Shipdaak order_items from local order fields.
    Shipdaak expects at least one item.
    """
    try:
        quantity = int(order.quantity or 1)
    except Exception:
        quantity = 1
    if quantity < 1:
        quantity = 1

    item_name = (order.item_type or "").strip() or (order.sku or "").strip() or "Item"

    try:
        price = float(order.item_amount or 0)
    except Exception:
        price = 0.0
    if price <= 0:
        try:
            price = float(order.order_value or 0)
        except Exception:
            price = 0.0
    if price <= 0:
        price = 1.0

    item: dict = {
        "name": item_name,
        "quantity": quantity,
        "price": price,
    }
    if order.sku:
        item["sku"] = str(order.sku)
    return [item]


def _max_bulk_orders() -> int:
    raw_limit = getattr(settings, "SHIPDAAK_LIVE_BULK_MAX_ORDERS", 50)
    try:
        parsed = int(raw_limit)
    except (TypeError, ValueError):
        parsed = 50
    return parsed if parsed > 0 else 50


def _normalize_order_ids(raw_ids) -> tuple[list[int], str | None]:
    if not isinstance(raw_ids, list) or not raw_ids:
        return [], "order_ids must be a non-empty list."

    unique_ids: list[int] = []
    seen: set[int] = set()
    for value in raw_ids:
        try:
            order_id = int(value)
        except (TypeError, ValueError):
            return [], "order_ids must contain valid integer IDs."
        if order_id <= 0:
            return [], "order_ids must contain positive integer IDs."
        if order_id in seen:
            continue
        seen.add(order_id)
        unique_ids.append(order_id)
    return unique_ids, None


class OrderViewSet(viewsets.ModelViewSet):
    """Order management ViewSet"""
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [IsAdminToken]

    def get_serializer_class(self):
        if self.action == 'partial_update' or self.action == 'update':
            return OrderUpdateSerializer
        return OrderSerializer

    def get_queryset(self):
        queryset = Order.objects.all()
        status_param = self.request.query_params.get('status')

        if status_param:
            try:
                queryset = queryset.filter(status=status_param)
            except ValueError:
                pass

        return queryset.order_by('-created_at')

    def create(self, request, *args, **kwargs):
        """Create a new local order. Optional Shipdaak pre-registration is feature-flagged."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Generate order number
        order_number = generate_order_number()

        # Create order locally
        order = serializer.save(
            order_number=order_number,
            status=OrderStatus.DRAFT
        )

        # ------------------------------------------------------------------
        # Optional legacy behavior:
        # pre-register order in ShipDaak (is_shipment_created=no) during
        # local order creation. Default is OFF to avoid duplicate upstream
        # records before AWB booking.
        #
        # Requires both:
        # - SHIPDAAK_ENABLE_BOOKING=true
        # - SHIPDAAK_REGISTER_ON_CREATE=true
        # ------------------------------------------------------------------
        should_register_on_create = (
            getattr(settings, 'SHIPDAAK_ENABLE_BOOKING', False)
            and getattr(settings, 'SHIPDAAK_REGISTER_ON_CREATE', False)
        )
        if should_register_on_create:
            import logging
            from ..integrations import ShipdaakV2Client
            from ..integrations.errors import ShipdaakIntegrationError
            _logger = logging.getLogger(__name__)
            try:
                client = ShipdaakV2Client()
                pickup_warehouse_id = None
                rto_warehouse_id = None

                if order.warehouse_id:
                    warehouse = order.warehouse
                    pickup_warehouse_id = warehouse.shipdaak_pickup_id
                    rto_warehouse_id = warehouse.shipdaak_rto_id

                    if not (pickup_warehouse_id and rto_warehouse_id):
                        warehouse_payload = client.create_warehouse(
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
                        pickup_warehouse_id, rto_warehouse_id = _extract_warehouse_ids(
                            warehouse_payload if isinstance(warehouse_payload, dict) else {}
                        )
                        if pickup_warehouse_id and rto_warehouse_id:
                            warehouse.shipdaak_pickup_id = pickup_warehouse_id
                            warehouse.shipdaak_rto_id = rto_warehouse_id
                            warehouse.shipdaak_synced_at = timezone.now()
                            warehouse.save(
                                update_fields=[
                                    "shipdaak_pickup_id",
                                    "shipdaak_rto_id",
                                    "shipdaak_synced_at",
                                    "updated_at",
                                ]
                            )

                result = client.register_order(
                    order_no=order.order_number,
                    pay_type=order.payment_mode,
                    weight_grams=int(order.weight * 1000),
                    length_cm=float(order.length),
                    breadth_cm=float(order.width),
                    height_cm=float(order.height),
                    recipient_name=order.recipient_name,
                    recipient_address=order.recipient_address,
                    recipient_pincode=str(order.recipient_pincode),
                    recipient_phone=order.recipient_contact,
                    recipient_city=order.recipient_city or '',
                    recipient_state=order.recipient_state or '',
                    total_amount=float(order.order_value or 0),
                    order_items=_build_shipdaak_order_items(order),
                    pickup_warehouse_id=pickup_warehouse_id,
                    rto_warehouse_id=rto_warehouse_id,
                )
                shipdaak_order_id = None
                if isinstance(result, dict):
                    shipdaak_order_id = (
                        result.get('orderId')
                        or (result.get('data') or {}).get('orderId')
                    )
                if shipdaak_order_id:
                    order.shipdaak_order_id = int(shipdaak_order_id)
                    order.save(update_fields=['shipdaak_order_id', 'updated_at'])
                    _logger.info(
                        'Order %s registered in ShipDaak as orderId=%s',
                        order.order_number, shipdaak_order_id,
                    )
            except ShipdaakIntegrationError as exc:
                logging.getLogger(__name__).warning(
                    'ShipDaak registration failed for order %s (non-fatal): %s',
                    order.order_number, exc,
                )
            except Exception as exc:
                logging.getLogger(__name__).error(
                    'Unexpected ShipDaak error for order %s (non-fatal): %s',
                    order.order_number, exc,
                )

        return Response(
            OrderSerializer(order).data,
            status=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        """Update an order - only DRAFT orders can be modified"""
        instance = self.get_object()
        if instance.status != OrderStatus.DRAFT:
             return Response(
                {"detail": f"Cannot update order in {instance.status} status. Only DRAFT orders can be modified."},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """Partial update an order - only DRAFT orders can be modified"""
        instance = self.get_object()
        if instance.status != OrderStatus.DRAFT:
             return Response(
                {"detail": f"Cannot update order in {instance.status} status. Only DRAFT orders can be modified."},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Delete an order - admins can delete orders in any status"""
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['post'], url_path='compare-carriers')
    def compare_carriers(self, request):
        """Compare carrier rates for one or more orders"""
        order_ids = request.data.get('order_ids', [])
        business_type = request.data.get('business_type')
        warehouse_id = request.data.get('courier_warehouse_id', request.data.get('warehouse_id'))

        if not order_ids:
            return Response(
                {"detail": "No orders provided"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            result = CarrierService.compare_rates(
                order_ids,
                business_type=business_type,
                warehouse_id=warehouse_id,
            )
        except BatchRouteValidationError as e:
            return Response(
                {"detail": str(e), "code": e.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValueError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_404_NOT_FOUND if "found" in str(e) else status.HTTP_400_BAD_REQUEST
            )

        # Format Response
        return Response({
            "orders": [
                {
                    "id": order.id,
                    "order_number": order.order_number,
                    "recipient_name": order.recipient_name,
                    "weight": order.applicable_weight or order.weight
                }
                for order in result["orders"]
            ],
            "carriers": result["carriers"],
            "source_pincode": result["source_pincode"],
            "source_warehouse": result.get("source_warehouse"),
            "source_courier_warehouse": result.get("source_courier_warehouse"),
            "dest_pincode": result["dest_pincode"],
            "total_weight": result["total_weight"]
        })


    @action(detail=False, methods=['post'], url_path='book-carrier')
    def book_carrier(self, request):
        """Book a carrier for selected orders"""
        serializer = CarrierSelectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            result = BookingService.book_orders(
                order_ids=data['order_ids'],
                carrier_name=data.get('carrier_name'),
                mode=data.get('mode'),
                carrier_id=data.get('carrier_id'),
                business_type=data.get('business_type'),
                use_global_account=data.get('use_global_account', False),
                warehouse_id=data.get('warehouse_id'),
            )
            return Response(result)
        except BatchRouteValidationError as e:
            return Response(
                {"detail": str(e), "code": e.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValueError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_404_NOT_FOUND if "found" in str(e) else status.HTTP_400_BAD_REQUEST
            )


    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel_order(self, request, pk=None):
        """
        Cancel a booking.
        Only BOOKED orders can be cancelled (not IN_TRANSIT or later).
        """
        order = self.get_object()

        # Cannot cancel orders that are IN_TRANSIT or later
        if order.status in [OrderStatus.PICKED_UP, OrderStatus.DELIVERED]:
            return Response(
                {"detail": f"Cannot cancel order in {order.status} status. Orders in transit or delivered cannot be cancelled."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Prevent cancelling already cancelled orders
        if order.status == OrderStatus.CANCELLED:
            return Response(
                {"detail": "Order is already cancelled"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Can only cancel BOOKED orders
        if order.status != OrderStatus.BOOKED:
            return Response(
                {"detail": f"Can only cancel orders in BOOKED status. Current status: {order.status}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            cancel_result = ShipdaakLifecycleService.cancel_order_upstream_first(order)
        except ShipdaakIntegrationError as exc:
            return Response(
                {
                    "detail": str(exc),
                    "order_number": order.order_number,
                    "current_status": order.status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            "status": "success",
            "message": f"Order {order.order_number} cancelled successfully",
            "order_number": order.order_number,
            "previous_status": cancel_result["previous_status"],
            "current_status": cancel_result["current_status"],
            "upstream_called": cancel_result["upstream_called"],
            "upstream_payload": cancel_result["upstream_payload"],
        })

    @action(detail=True, methods=["post"], url_path="shipdaak/sync-status")
    def shipdaak_sync_status(self, request, pk=None):
        """Fetch live Shipdaak tracking for an order and refresh local status."""
        order = self.get_object()
        if not order.awb_number:
            return Response(
                {"detail": "Order has no AWB."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            sync_result = ShipdaakLifecycleService.sync_order_status(order)
        except (ShipdaakIntegrationError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "status": "success",
                "order_number": order.order_number,
                "awb_number": order.awb_number,
                "upstream_status": sync_result["upstream_status"],
                "mapped_status": sync_result["mapped_status"],
                "status_updated": sync_result["status_updated"],
                "previous_status": sync_result["previous_status"],
                "current_status": sync_result["current_status"],
                "upstream_payload": sync_result["tracking_payload"],
            }
        )

    @action(detail=False, methods=["post"], url_path="shipdaak/sync-statuses")
    def shipdaak_sync_statuses(self, request):
        """Sync live Shipdaak tracking for multiple orders with partial results."""
        order_ids, error = _normalize_order_ids(request.data.get("order_ids"))
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        limit = _max_bulk_orders()
        if len(order_ids) > limit:
            return Response(
                {
                    "detail": f"At most {limit} orders can be synced in one request.",
                    "code": "batch_limit_exceeded",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        orders = list(Order.objects.filter(id__in=order_ids))
        found_ids = {order.id for order in orders}
        missing_ids = [order_id for order_id in order_ids if order_id not in found_ids]
        if missing_ids:
            return Response(
                {"detail": f"One or more orders not found. Missing IDs: {missing_ids}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        orders_by_id = {order.id: order for order in orders}

        scanned = 0
        updated = 0
        unchanged = 0
        skipped = 0
        failed = 0

        updated_orders: list[dict] = []
        unchanged_orders: list[dict] = []
        skipped_orders: list[dict] = []
        failed_orders: list[dict] = []

        for order_id in order_ids:
            order = orders_by_id[order_id]
            scanned += 1

            if not order.awb_number:
                skipped += 1
                skipped_orders.append(
                    {
                        "order_id": order.id,
                        "order_number": order.order_number,
                        "status": order.status,
                        "reason": "missing_awb",
                    }
                )
                continue

            if order.status not in ShipdaakLifecycleService.ACTIVE_SYNC_STATUSES:
                skipped += 1
                skipped_orders.append(
                    {
                        "order_id": order.id,
                        "order_number": order.order_number,
                        "status": order.status,
                        "reason": "ineligible_status",
                    }
                )
                continue

            try:
                sync_result = ShipdaakLifecycleService.sync_order_status(order)
                payload = {
                    "order_id": order.id,
                    "order_number": order.order_number,
                    "from_status": sync_result["previous_status"],
                    "to_status": sync_result["current_status"],
                    "upstream_status": sync_result.get("upstream_status"),
                    "mapped_status": sync_result.get("mapped_status"),
                }
                if sync_result["status_updated"]:
                    updated += 1
                    updated_orders.append(payload)
                else:
                    unchanged += 1
                    unchanged_orders.append(payload)
            except (ShipdaakIntegrationError, ValueError) as exc:
                failed += 1
                failed_orders.append(
                    {
                        "order_id": order.id,
                        "order_number": order.order_number,
                        "status": order.status,
                        "error": str(exc),
                    }
                )
            except Exception as exc:
                failed += 1
                failed_orders.append(
                    {
                        "order_id": order.id,
                        "order_number": order.order_number,
                        "status": order.status,
                        "error": f"Unexpected error: {exc}",
                    }
                )

        summary_status = "success"
        if failed > 0 or skipped > 0:
            summary_status = "partial_success"

        return Response(
            {
                "status": summary_status,
                "scanned": scanned,
                "updated": updated,
                "unchanged": unchanged,
                "skipped": skipped,
                "failed": failed,
                "updated_orders": updated_orders,
                "unchanged_orders": unchanged_orders,
                "skipped_orders": skipped_orders,
                "failed_orders": failed_orders,
            }
        )

