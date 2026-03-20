"""
FTL (Full Truck Load) Views.
Contains FTL order management and rate calculation endpoints.
"""
from rest_framework import viewsets, status, serializers as drf_serializers
from rest_framework.decorators import api_view, action, permission_classes
from rest_framework.response import Response
from django.utils import timezone

from ..models import FTLOrder, OrderStatus
from ..permissions import IsAdminToken, IsCourierOperator
from ..serializers import FTLOrderSerializer, FTLRateRequestSerializer
from .base import (
    load_ftl_rates, calculate_ftl_price, generate_ftl_order_number, logger
)


@api_view(['GET'])
@permission_classes([IsCourierOperator])
def get_ftl_routes(request):
    """Get all available FTL routes (source and destination cities)"""
    ftl_rates = load_ftl_rates()

    # Build a structure with source cities and their destinations + container types
    routes = {}
    for source_city, destinations in ftl_rates.items():
        routes[source_city] = {}
        for dest_city, rates in destinations.items():
            routes[source_city][dest_city] = list(rates.keys())

    return Response(routes)


@api_view(['POST'])
@permission_classes([IsCourierOperator])
def calculate_ftl_rate(request):
    """Calculate FTL rate for given source, destination and container type"""
    serializer = FTLRateRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    
    ftl_rates = load_ftl_rates()
    source_city = data['source_city']
    destination_city = data['destination_city']
    container_type = data['container_type']
    
    # Get base price from rates
    if source_city not in ftl_rates:
        return Response(
            {"detail": f"Source city '{source_city}' not found in FTL rates"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    if destination_city not in ftl_rates[source_city]:
        return Response(
            {"detail": f"Destination city '{destination_city}' not found for source '{source_city}'"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    container_rates = ftl_rates[source_city][destination_city]
    
    if container_type not in container_rates:
        return Response(
            {"detail": f"Container type '{container_type}' not available for {source_city} to {destination_city}"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    base_price = container_rates[container_type]
    pricing = calculate_ftl_price(base_price)
    
    return Response({
        "source_city": source_city,
        "destination_city": destination_city,
        "container_type": container_type,
        **pricing
    })


class FTLOrderViewSet(viewsets.ModelViewSet):
    """FTL Order management ViewSet"""
    queryset = FTLOrder.objects.all()
    serializer_class = FTLOrderSerializer
    permission_classes = [IsAdminToken]
    
    def get_queryset(self):
        queryset = FTLOrder.objects.all()
        status_param = self.request.query_params.get('status')
        
        if status_param:
            try:
                queryset = queryset.filter(status=status_param)
            except ValueError:
                pass
        
        return queryset.order_by('-created_at')
    
    def create(self, request, *args, **kwargs):
        """Create a new FTL order"""
        try:
            # First calculate the rate
            source_city = request.data.get('source_city')
            destination_city = request.data.get('destination_city')
            container_type = request.data.get('container_type')

            if not all([source_city, destination_city, container_type]):
                return Response(
                    {"detail": "source_city, destination_city, and container_type are required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            ftl_rates = load_ftl_rates()

            if source_city not in ftl_rates or destination_city not in ftl_rates[source_city]:
                return Response(
                    {"detail": "Rate not found for the specified route and container type"},
                    status=status.HTTP_404_NOT_FOUND
                )

            container_rates = ftl_rates[source_city][destination_city]

            if container_type not in container_rates:
                return Response(
                    {"detail": f"Container type '{container_type}' not available for this route"},
                    status=status.HTTP_404_NOT_FOUND
                )

            base_price = container_rates[container_type]
            pricing = calculate_ftl_price(base_price)

            # Generate order number
            order_number = generate_ftl_order_number()

            # Prepare data for serializer (excluding pricing fields which are read-only)
            order_data = request.data.copy()

            serializer = self.get_serializer(data=order_data)
            serializer.is_valid(raise_exception=True)

            # Save with the calculated pricing fields and order number
            order = serializer.save(
                order_number=order_number,
                status=OrderStatus.DRAFT,
                **pricing
            )

            return Response(
                FTLOrderSerializer(order).data,
                status=status.HTTP_201_CREATED
            )
        except drf_serializers.ValidationError:
            # Re-raise validation errors so DRF handles them properly
            raise
        except Exception as e:
            logger.error(f"FTL_ORDER_ERROR: Failed to create FTL order: {str(e)}")
            logger.exception(e)
            return Response(
                {"detail": f"Failed to create FTL order: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def update(self, request, *args, **kwargs):
        """Update an FTL order - only allowed for DRAFT orders"""
        order = self.get_object()

        # Only DRAFT orders can be edited
        if order.status != OrderStatus.DRAFT:
            return Response(
                {"detail": "You can only edit orders in DRAFT status"},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """Partial update an FTL order - only allowed for DRAFT orders"""
        order = self.get_object()

        # Only DRAFT orders can be edited
        if order.status != OrderStatus.DRAFT:
            return Response(
                {"detail": "You can only edit orders in DRAFT status"},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().partial_update(request, *args, **kwargs)

    @action(detail=False, methods=['post'], url_path='book')
    def book_ftl_orders(self, request):
        """Book multiple FTL orders (change status from DRAFT to BOOKED)"""
        order_ids = request.data.get('order_ids', [])

        if not order_ids:
            return Response(
                {"detail": "No order IDs provided"},
                status=status.HTTP_400_BAD_REQUEST
            )

        orders = FTLOrder.objects.filter(id__in=order_ids)

        if orders.count() != len(order_ids):
            return Response(
                {"detail": "One or more orders not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check all orders are in DRAFT status
        non_draft_orders = [order for order in orders if order.status != OrderStatus.DRAFT]
        if non_draft_orders:
            return Response(
                {"detail": f"Only DRAFT orders can be booked. {len(non_draft_orders)} order(s) are not in DRAFT status"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update all orders to BOOKED status
        for order in orders:
            order.status = OrderStatus.BOOKED
            order.booked_at = timezone.now()
            order.save()

        return Response({
            "status": "success",
            "message": f"{orders.count()} FTL order(s) booked successfully",
            "orders_booked": [order.order_number for order in orders]
        })

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel_order(self, request, pk=None):
        """
        Cancel an FTL booking.
        Only BOOKED orders can be cancelled.
        """
        order = self.get_object()

        # Cannot cancel orders that are IN_TRANSIT or later
        if order.status in [OrderStatus.PICKED_UP, OrderStatus.DELIVERED]:
            return Response(
                {"detail": f"Cannot cancel order in {order.status} status. Orders in transit or delivered cannot be cancelled."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Can only cancel BOOKED orders
        if order.status != OrderStatus.BOOKED:
            return Response(
                {"detail": f"Can only cancel orders in BOOKED status. Current status: {order.status}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Prevent cancelling already cancelled orders
        if order.status == OrderStatus.CANCELLED:
            return Response(
                {"detail": "Order is already cancelled"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Cancel the order
        previous_status = order.status
        order.status = OrderStatus.CANCELLED
        order.save()

        return Response({
            "status": "success",
            "message": f"Order {order.order_number} cancelled successfully",
            "order_number": order.order_number,
            "previous_status": previous_status,
            "current_status": order.status
        })

    def destroy(self, request, *args, **kwargs):
        """Delete an FTL order - allowed for DRAFT or CANCELLED orders"""
        order = self.get_object()

        if order.status not in [OrderStatus.DRAFT, OrderStatus.CANCELLED]:
            return Response(
                {"detail": "You can only delete orders in DRAFT or CANCELLED status"},
                status=status.HTTP_403_FORBIDDEN
            )

        order.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
