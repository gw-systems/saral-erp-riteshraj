"""
Admin Views.
Contains admin endpoints for rate card management.
"""
from rest_framework.decorators import api_view, permission_classes, throttle_classes, parser_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
from django.conf import settings
import os
import tempfile
from django.core.management import call_command
from django.db.models import Q

from ..models import Order, FTLOrder, Courier, CourierZoneRate
from ..permissions import IsCourierManager, user_can_manage_courier
from ..serializers import NewCarrierSerializer, OrderSerializer, FTLOrderSerializer
from .base import (
    load_rates, invalidate_rates_cache, logger
)

DEFAULT_LIST_LIMIT = 100
MAX_LIST_LIMIT = 500


def _find_courier_by_identifier(carrier_name: str):
    """Resolve courier by stable code, internal name, display name, or rendered carrier label."""
    courier = Courier.objects.filter(
        Q(courier_code__iexact=carrier_name)
        | Q(name__iexact=carrier_name)
        | Q(display_name__iexact=carrier_name)
    ).first()
    if courier:
        return courier

    target = (carrier_name or "").strip().lower()
    if not target:
        return None
    for item in Courier.objects.all():
        if str(item).strip().lower() == target:
            return item
    return None


def _parse_limit(raw_value):
    try:
        limit = int(raw_value)
    except (TypeError, ValueError):
        raise ValueError("Invalid 'limit' parameter. Must be an integer.")
    if limit < 1:
        raise ValueError("Invalid 'limit' parameter. Must be >= 1.")
    if limit > MAX_LIST_LIMIT:
        raise ValueError(f"Invalid 'limit' parameter. Maximum allowed is {MAX_LIST_LIMIT}.")
    return limit


def _validate_excel_upload(excel_file):
    name = (excel_file.name or "").lower()
    if not name.endswith((".xlsx", ".xls")):
        raise ValueError("Invalid file format. Only .xlsx or .xls files are allowed.")
    max_size = int(getattr(settings, "MAX_RATE_UPLOAD_SIZE_BYTES", 10 * 1024 * 1024))
    if excel_file.size > max_size:
        max_mb = max_size / (1024 * 1024)
        raise ValueError(f"File too large. Maximum allowed size is {max_mb:.1f} MB.")


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([AnonRateThrottle])
def admin_login(request):
    """
    ERP-native session handshake endpoint.

    The standalone courier password flow is intentionally disabled once courier
    is absorbed into the ERP. Frontends should rely on the existing ERP login
    session instead of a second admin credential.
    """
    if not request.user.is_authenticated:
        return Response(
            {"detail": "ERP login required.", "auth_mode": "erp_session"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if not user_can_manage_courier(request.user):
        return Response(
            {"detail": "You do not have permission to access courier admin APIs."},
            status=status.HTTP_403_FORBIDDEN,
        )

    return Response(
        {
            "status": "success",
            "token": None,
            "auth_mode": "erp_session",
            "expires_in_seconds": None,
            "user": request.user.get_full_name() or request.user.username,
        }
    )


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_logout(request):
    """
    No-op logout endpoint kept only for backward compatibility.

    Courier now uses the ERP session. Logging out should happen through the ERP
    account flow, not a courier-local endpoint.
    """
    return Response({"status": "success", "auth_mode": "erp_session"})


@api_view(['GET'])
@permission_classes([IsCourierManager])
def get_all_rates(request):
    """Get all carrier rates from database"""
    rates = load_rates()
    return Response(rates)


@api_view(['POST'])
@permission_classes([IsCourierManager])
def update_rates(request):
    """
    DEPRECATED: Update carrier rates via JSON file.
    Rates are now managed via Django Admin or database models.
    This endpoint is kept for backward compatibility but does nothing.
    """
    logger.warning("ADMIN_ACTION: Deprecated update_rates endpoint called. Use Django Admin instead.")
    invalidate_rates_cache()  # Clear cache in case rates were updated via admin
    return Response({
        "status": "success",
        "message": "Rates updated successfully"
    })


@api_view(['POST'])
@permission_classes([IsCourierManager])
def add_carrier(request):
    """Add a new carrier to the database"""
    serializer = NewCarrierSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    carrier_data = serializer.validated_data

    try:
        # Check for duplicate carrier name in DB
        if Courier.objects.filter(name__iexact=carrier_data['carrier_name']).exists():
            logger.warning(f"ADMIN_ACTION: Duplicate carrier name attempted: {carrier_data['carrier_name']}")
            return Response(
                {"detail": f"Carrier '{carrier_data['carrier_name']}' already exists."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create Courier using Manager helper
        # Mapping serializer fields to Manager fields
        # Serializer: carrier_name, mode, min_weight, forward_rates, additional_rates, cod_fixed, cod_percent
        # Manager args: name, mode (as carrier_mode), min_weight, cod_charge_fixed, cod_charge_percent
        
        courier = Courier.objects.create(
            name=carrier_data['carrier_name'],
            carrier_mode=carrier_data['mode'],
            min_weight=carrier_data['min_weight'],
            cod_charge_fixed=carrier_data.get('cod_fixed', 0.0),
            cod_charge_percent=carrier_data.get('cod_percent', 0.0),
            # Defaults
            carrier_type="B2C",
            is_active=carrier_data.get('active', True)
        )
        
        # Manually create rates
        forward_rates = carrier_data.get('forward_rates', {})
        additional_rates = carrier_data.get('additional_rates', {})
        
        # Iterate over zone codes (z_a, z_b...)
        for zone_code, rate_val in forward_rates.items():
            CourierZoneRate.objects.create(
                courier=courier,
                zone_code=zone_code,
                rate_type='forward',
                rate=rate_val
            )
            
        for zone_code, rate_val in additional_rates.items():
            CourierZoneRate.objects.create(
                courier=courier,
                zone_code=zone_code,
                rate_type='additional',
                rate=rate_val
            )

        logger.info(f"ADMIN_ACTION: New carrier added to DB: {courier.name}")
        invalidate_rates_cache()
        
        return Response({
            "status": "success",
            "message": f"Carrier '{courier.name}' added successfully",
            "carrier": {
                "id": courier.id,
                "name": courier.name,
                "mode": courier.carrier_mode
            }
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        logger.error(f"ADMIN_ERROR: Failed to add carrier: {str(e)}")
        return Response(
            {"detail": f"Failed to add carrier: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsCourierManager])
def toggle_carrier_active(request, carrier_name):
    """Toggle carrier active/inactive status"""
    active = request.data.get('active')

    if active is None:
        return Response(
            {"detail": "Missing 'active' parameter"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        courier = _find_courier_by_identifier(carrier_name)
        if not courier:
            return Response(
                {"detail": f"Carrier '{carrier_name}' not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        if isinstance(active, str):
            active = active.strip().lower() in {"true", "1", "yes", "y"}
        courier.is_active = bool(active)
        courier.save(update_fields=["is_active", "updated_at"])

        logger.info(f"ADMIN_ACTION: Carrier '{courier.name}' {'activated' if active else 'deactivated'}")
        invalidate_rates_cache()
        return Response({
            "status": "success",
            "message": f"Carrier '{courier.name}' {'activated' if active else 'deactivated'}",
            "carrier_name": courier.name,
            "active": courier.is_active
        })
    except Exception as e:
        logger.error(f"ADMIN_ERROR: Failed to toggle carrier status: {str(e)}")
        return Response(
            {"detail": f"Failed to toggle carrier status: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsCourierManager])
def delete_carrier(request, carrier_name):
    """Delete a carrier from rate cards"""
    try:
        courier = _find_courier_by_identifier(carrier_name)
        if not courier:
            return Response(
                {"detail": f"Carrier '{carrier_name}' not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        deleted_name = courier.name
        courier.delete()

        logger.info(f"ADMIN_ACTION: Carrier '{deleted_name}' deleted")
        invalidate_rates_cache()
        return Response({
            "status": "success",
            "message": f"Carrier '{deleted_name}' deleted successfully",
            "remaining_carriers": Courier.objects.count()
        })

    except Exception as e:
        logger.error(f"ADMIN_ERROR: Failed to delete carrier: {str(e)}")
        return Response(
            {"detail": f"Failed to delete carrier: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PATCH'])
@permission_classes([IsCourierManager])
def update_carrier(request, carrier_name):
    """Update carrier details"""
    try:
        courier = _find_courier_by_identifier(carrier_name)
        if not courier:
            return Response(
                {"detail": f"Carrier '{carrier_name}' not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = NewCarrierSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        update_data = serializer.validated_data

        if "carrier_name" in update_data:
            courier.name = update_data["carrier_name"]
            if not courier.display_name:
                courier.display_name = update_data["carrier_name"]
        if "mode" in update_data:
            courier.carrier_mode = update_data["mode"]
        if "active" in update_data:
            courier.is_active = update_data["active"]
        if "min_weight" in update_data and hasattr(courier, "constraints_config"):
            courier.constraints_config.min_weight = update_data["min_weight"]
            courier.constraints_config.save(update_fields=["min_weight"])
        if "cod_fixed" in update_data and hasattr(courier, "fees_config"):
            courier.fees_config.cod_fixed = update_data["cod_fixed"]
            courier.fees_config.save(update_fields=["cod_fixed"])
        if "cod_percent" in update_data and hasattr(courier, "fees_config"):
            courier.fees_config.cod_percent = update_data["cod_percent"]
            courier.fees_config.save(update_fields=["cod_percent"])
        courier.save()

        rate_updates = []
        for zone_code, rate_val in update_data.get("forward_rates", {}).items():
            rate_updates.append((zone_code, CourierZoneRate.RateType.FORWARD, rate_val))
        for zone_code, rate_val in update_data.get("additional_rates", {}).items():
            rate_updates.append((zone_code, CourierZoneRate.RateType.ADDITIONAL, rate_val))
        for zone_code, rate_type, rate_val in rate_updates:
            CourierZoneRate.objects.update_or_create(
                courier=courier,
                zone_code=zone_code,
                rate_type=rate_type,
                defaults={"rate": rate_val},
            )

        logger.info(f"ADMIN_ACTION: Carrier '{courier.name}' updated")
        invalidate_rates_cache()
        return Response({
            "status": "success",
            "message": f"Carrier '{courier.name}' updated successfully",
            "carrier": {
                "id": courier.id,
                "name": courier.name,
                "mode": courier.carrier_mode,
                "active": courier.is_active,
            }
        })

    except Exception as e:
        logger.error(f"ADMIN_ERROR: Failed to update carrier: {str(e)}")
        return Response(
            {"detail": f"Failed to update carrier: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsCourierManager])
def admin_orders_list(request):
    """Get all orders for admin dashboard with filtering"""

    # Get query params
    status_filter = request.query_params.get('status')
    carrier_filter = request.query_params.get('carrier')
    try:
        limit = _parse_limit(request.query_params.get('limit', DEFAULT_LIST_LIMIT))
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    # Build queryset
    queryset = Order.objects.all().order_by('-created_at')

    if status_filter:
        queryset = queryset.filter(status=status_filter)
    if carrier_filter:
        queryset = queryset.filter(carrier__name=carrier_filter)

    # Get orders
    orders = queryset[:limit]

    return Response({
        "count": queryset.count(),
        "orders": OrderSerializer(orders, many=True).data
    })


@api_view(['POST'])
@permission_classes([IsCourierManager])
@parser_classes([MultiPartParser, FormParser])
def upload_excel_rates(request):
    """Upload Excel Rate Card and import rates into DB"""
    if 'file' not in request.FILES:
        return Response(
            {"detail": "No file explicitly provided under 'file' key."},
            status=status.HTTP_400_BAD_REQUEST
        )

    excel_file = request.FILES['file']
    try:
        _validate_excel_upload(excel_file)
    except ValueError as exc:
        return Response(
            {"detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Save file to a temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            for chunk in excel_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        # Run the management command
        try:
            call_command('import_rates', tmp_path)
            logger.info(f"ADMIN_ACTION: Successfully imported rates from {excel_file.name}")
            invalidate_rates_cache()
            
            # Optionally, you can capture the output of call_command and return it
            return Response({
                "status": "success",
                "message": f"Successfully imported rates from {excel_file.name}!"
            })
        except Exception as e:
            logger.error(f"ADMIN_ERROR: Import process failed: {str(e)}")
            return Response(
                {"detail": f"Failed to import rates: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    except Exception as e:
        logger.error(f"ADMIN_ERROR: File processing failed: {str(e)}")
        return Response(
            {"detail": f"File processing error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsCourierManager])
@parser_classes([MultiPartParser, FormParser])
def upload_ftl_excel_rates(request):
    """Upload FTL Excel Rate Card and import rates into DB"""
    if 'file' not in request.FILES:
        return Response(
            {"detail": "No file explicitly provided under 'file' key."},
            status=status.HTTP_400_BAD_REQUEST
        )

    excel_file = request.FILES['file']
    try:
        _validate_excel_upload(excel_file)
    except ValueError as exc:
        return Response(
            {"detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Save file to a temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            for chunk in excel_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        # Run the management command
        try:
            call_command('import_ftl_rates', excel_file=tmp_path)
            logger.info(f"ADMIN_ACTION: Successfully imported FTL rates from {excel_file.name}")
            
            return Response({
                "status": "success",
                "message": f"Successfully imported FTL rates from {excel_file.name}!"
            })
        except Exception as e:
            logger.error(f"ADMIN_ERROR: FTL Import process failed: {str(e)}")
            return Response(
                {"detail": f"Failed to import FTL rates: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    except Exception as e:
        logger.error(f"ADMIN_ERROR: FTL File processing failed: {str(e)}")
        return Response(
            {"detail": f"FTL File processing error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsCourierManager])
def admin_ftl_orders_list(request):
    """Get all FTL orders for admin dashboard"""

    # Get query params
    status_filter = request.query_params.get('status')
    try:
        limit = _parse_limit(request.query_params.get('limit', DEFAULT_LIST_LIMIT))
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    # Build queryset
    queryset = FTLOrder.objects.all().order_by('-created_at')

    if status_filter:
        queryset = queryset.filter(status=status_filter)

    # Get orders
    orders = queryset[:limit]

    return Response({
        "count": queryset.count(),
        "orders": FTLOrderSerializer(orders, many=True).data
    })


@api_view(['GET'])
@permission_classes([IsCourierManager])
def admin_dashboard_stats(request):
    """Get dashboard statistics for admin"""
    from django.utils import timezone
    from datetime import timedelta

    today = timezone.now().date()
    last_30_days = today - timedelta(days=30)

    # Order stats
    order_stats = Order.objects.aggregate(
        total_orders=Count('id'),
        total_revenue=Sum('total_cost'),
    )

    # Orders by status
    status_counts = Order.objects.values('status').annotate(
        count=Count('id')
    ).order_by('status')

    # Carrier performance
    carrier_stats = Order.objects.exclude(
        carrier__isnull=True
    ).values('carrier__name').annotate(
        order_count=Count('id'),
        revenue=Sum('total_cost')
    ).order_by('-order_count')[:10]

    # FTL stats
    ftl_stats = FTLOrder.objects.aggregate(
        total_orders=Count('id'),
        total_revenue=Sum('total_price'),
    )

    # Recent activity (last 30 days)
    recent_orders = Order.objects.filter(
        created_at__date__gte=last_30_days
    ).count()

    recent_booked = Order.objects.filter(
        status=OrderStatus.BOOKED,
        booked_at__date__gte=last_30_days
    ).count()

    # Active/inactive carrier totals must come from DB queryset counts.
    total_carriers = Courier.objects.count()
    active_carriers = Courier.objects.filter(is_active=True).count()

    return Response({
        "orders": {
            "total": order_stats['total_orders'] or 0,
            "total_revenue": float(order_stats['total_revenue'] or 0),
            "by_status": {item['status']: item['count'] for item in status_counts},
            "recent_30_days": recent_orders,
            "booked_30_days": recent_booked,
        },
        "ftl_orders": {
            "total": ftl_stats['total_orders'] or 0,
            "total_revenue": float(ftl_stats['total_revenue'] or 0),
        },
        "carriers": {
            "total": total_carriers,
            "active": active_carriers,
            "inactive": total_carriers - active_carriers,
            "performance": list(carrier_stats),
        },
        "generated_at": timezone.now().isoformat(),
    })


@api_view(['GET', 'PUT'])
@permission_classes([IsCourierManager])
def system_settings(request):
    """Get or update global system settings"""
    from decimal import Decimal

    config = SystemConfig.get_solo()

    if request.method == 'GET':
        return Response({
            "GST_RATE": float(config.gst_rate),
            "ESCALATION_RATE": float(config.escalation_rate),
            "VOLUMETRIC_DIVISOR": int(getattr(config, 'volumetric_divisor', 5000)),
            "DEFAULT_WEIGHT_SLAB": float(getattr(config, 'default_weight_slab', 0.5)),
            "DIESEL_PRICE": float(config.diesel_price_current),
        })

    elif request.method == 'PUT':
        data = request.data
        try:
            if 'GST_RATE' in data:
                config.gst_rate = Decimal(str(data['GST_RATE']))
            if 'ESCALATION_RATE' in data:
                config.escalation_rate = Decimal(str(data['ESCALATION_RATE']))
            if 'VOLUMETRIC_DIVISOR' in data:
                if hasattr(config, 'volumetric_divisor'):
                    config.volumetric_divisor = int(data['VOLUMETRIC_DIVISOR'])
            if 'DEFAULT_WEIGHT_SLAB' in data:
                if hasattr(config, 'default_weight_slab'):
                    config.default_weight_slab = Decimal(str(data['DEFAULT_WEIGHT_SLAB']))
            if 'DIESEL_PRICE' in data:
                config.diesel_price_current = Decimal(str(data['DIESEL_PRICE']))
            
            config.save()
            invalidate_rates_cache()
            
            logger.info("ADMIN_ACTION: System settings updated")
            return Response({"status": "success", "message": "Settings updated successfully"})
        except Exception as e:
            logger.error(f"ADMIN_ERROR: Failed to update settings: {str(e)}")
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
