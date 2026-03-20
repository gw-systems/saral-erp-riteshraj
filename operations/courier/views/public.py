"""
Public API Views.
Contains health check, rate comparison, and pincode lookup endpoints.
"""
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework import status
from django.shortcuts import render, redirect

from .base import (
    load_rates, logger, RateRequestSerializer,
    get_zone_column, calculate_cost
)
from django.conf import settings
from ..exceptions import InvalidWeightError, CourierError
from ..models import Pincode, Courier
from ..permissions import IsCourierOperator

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Health check endpoint for monitoring"""
    pincode_count = Pincode.objects.count()
    rate_cars = load_rates()
    return Response({
        "status": "healthy",
        "pincode_db_loaded": pincode_count > 0,
        "pincode_count": pincode_count,
        "rate_cards_loaded": len(rate_cars) > 0,
        "rate_card_count": len(rate_cars)
    })


def dashboard_view(request):
    """Render the main dashboard (Django template)"""
    return render(request, 'dashboard.html', {'section': 'dashboard'})


def rate_calculator_view(request):
    """Render the dashboard with rate calculator active by default"""
    return render(request, 'dashboard.html', {'section': 'rate-calculator'})


def login_view(request):
    """Render lightweight admin auth login page for dashboard/admin APIs"""
    return render(request, 'login.html')


@api_view(['GET'])
@permission_classes([AllowAny])
def root_redirect(request):
    """Redirect to dashboard"""
    return redirect('/dashboard/')


@api_view(['POST'])
@throttle_classes([AnonRateThrottle])
@permission_classes([IsCourierOperator])
def compare_rates(request):
    """Compare shipping rates across carriers"""
    serializer = RateRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    zone_key, zone_label = get_zone_column(
        data['source_pincode'],
        data['dest_pincode']
    )

    # Calculate Total Weight
    if data.get('orders'):
        # Multi-box logic
        try:
            # Load Volumetric Divisor from Config
            vol_divisor = settings.COURIER_BUSINESS_RULES.get('VOLUMETRIC_DIVISOR', 5000)
        except Exception:
            vol_divisor = 5000 # Fallback

        total_weight = 0
        for box in data['orders']:
            vol_weight = (box['length'] * box['width'] * box['height']) / vol_divisor
            applicable = max(box['weight'], vol_weight)
            total_weight += applicable
    else:
        # Legacy single weight logic
        total_weight = data['weight']

    rates = load_rates()

    # Filter by Category
    requested_category = data.get('category')
    if requested_category:
        # Normalize for comparison
        # e.g. "RVP" from UI matching "RVP" in DB
        rates = [r for r in rates if r.get('service_category', '').lower() == requested_category.lower()]

    results = []
    business_type = str(data.get('business_type') or '').strip().lower()  # 'b2c' or 'b2b'
    if business_type in {"b2c", "b2b"}:
        allowed_courier_ids = set(
            Courier.objects.filter(is_active=True, carrier_type__iexact=business_type)
            .values_list("id", flat=True)
        )
        rates = [rate for rate in rates if rate.get("id") in allowed_courier_ids]

    for carrier in rates:
        if not carrier.get("active", True):
            continue

        # Existing per-carrier constraints
        min_weight = carrier.get('min_weight', 0)
        # Ensure min_weight is float
        try:
            min_weight = float(min_weight)
        except (ValueError, TypeError):
            min_weight = 0.0

        req_mode = data['mode'].lower()
        car_mode = carrier.get("mode", "Surface").lower()
        if req_mode != "both" and car_mode != req_mode:
            continue
            
        # Determine Rate Type (Forward vs Reverse)
        # Default is forward. If category is RVP, use reverse.
        rate_type = 'forward'
        if carrier.get('service_category') == 'RVP':
            rate_type = 'reverse'

        try:
            res = calculate_cost(
                weight=total_weight,
                source_pincode=data['source_pincode'],
                dest_pincode=data['dest_pincode'],
                carrier_data=carrier,
                is_cod=data['is_cod'],
                order_value=data['order_value'],
                rate_type=rate_type
            )


            res["applied_zone"] = res.get("zone", "") # Use zone from engine result
            res["mode"] = carrier.get("mode", "Surface")
            res["service_category"] = carrier.get("service_category", "")
            results.append(res)
        except InvalidWeightError as e:
            # If weight is invalid, it's a bad request for ALL carriers
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except CourierError as e:
            # Known courier error (e.g. pinned logic failure), log and skip
            logger.warning(f"Carrier {carrier.get('carrier_name')} skipped: {e.message}")
            continue
        except Exception as e:
            logger.error(f"CALCULATION_ERROR: Carrier {carrier.get('carrier_name')} failed. Error: {str(e)}")
            continue

    # Filter out non-servicable carriers before sorting
    valid_results = [r for r in results if r.get("serviceable")]

    # Sort results by price
    valid_results.sort(key=lambda x: x["total_cost"])
    
    # Deduplicate exact identical output names and prices
    deduped_results = []
    seen_keys = set()
    
    for res in valid_results:
        carrier_name = res.get("carrier", "")
        dedup_key = f"{carrier_name}_{res['total_cost']}"
        
        if dedup_key not in seen_keys:
            seen_keys.add(dedup_key)
            deduped_results.append(res)

    if not deduped_results:
        logger.warning(f"No serviceable carriers matched for mode: {data['mode']}")
        return Response(
            {"detail": f"No serviceable carriers found for this route."},
            status=status.HTTP_404_NOT_FOUND
        )

    return Response(sorted(deduped_results, key=lambda x: x["total_cost"]))


@api_view(['GET'])
@permission_classes([AllowAny])
def lookup_pincode(request, pincode):
    """Get city and state for a pincode"""
    try:
        pincode_obj = Pincode.objects.get(pincode=int(pincode))
        return Response({
            "pincode": pincode,
            "city": pincode_obj.district,
            "state": pincode_obj.state,
            "office": pincode_obj.office_name
        })
    except Pincode.DoesNotExist:
        return Response(
            {"detail": "Pincode not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error looking up pincode {pincode}: {e}")
        return Response(
             {"detail": "Error processing request"},
             status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
