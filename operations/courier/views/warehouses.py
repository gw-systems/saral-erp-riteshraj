"""Courier warehouse API endpoints."""

from rest_framework import viewsets

from ..models import Warehouse
from ..permissions import IsAdminToken
from ..serializers import WarehouseSerializer


class WarehouseViewSet(viewsets.ModelViewSet):
    """CRUD APIs for courier-only warehouses."""

    queryset = Warehouse.objects.all().order_by("-created_at")
    serializer_class = WarehouseSerializer
    permission_classes = [IsAdminToken]
