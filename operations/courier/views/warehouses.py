"""Courier warehouse API endpoints."""

from django.db import IntegrityError, connection, transaction
from rest_framework import status, viewsets
from rest_framework.response import Response

from ..models import Warehouse
from ..permissions import IsAdminToken
from ..serializers import WarehouseSerializer


def _reset_warehouse_pk_sequence() -> None:
    """Align the warehouse PK sequence with the current max local warehouse id."""
    table_name = Warehouse._meta.db_table
    pk_column = Warehouse._meta.pk.column

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_get_serial_sequence(%s, %s)", [table_name, pk_column])
        sequence_name = cursor.fetchone()[0]
        if not sequence_name:
            return

        cursor.execute(f"SELECT COALESCE(MAX({pk_column}), 0) FROM {table_name}")
        max_id = int(cursor.fetchone()[0] or 0)
        if max_id > 0:
            cursor.execute("SELECT setval(%s, %s, true)", [sequence_name, max_id])
        else:
            cursor.execute("SELECT setval(%s, %s, false)", [sequence_name, 1])


class WarehouseViewSet(viewsets.ModelViewSet):
    """CRUD APIs for courier-only warehouses."""

    queryset = Warehouse.objects.all().order_by("-created_at")
    serializer_class = WarehouseSerializer
    permission_classes = [IsAdminToken]

    def create(self, request, *args, **kwargs):
        """
        Create a local courier warehouse.

        If the underlying Postgres sequence drifts behind the actual table IDs,
        retry once after realigning the sequence so the operator gets a normal
        success response instead of a 500.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        for attempt in range(2):
            try:
                with transaction.atomic():
                    self.perform_create(serializer)
                headers = self.get_success_headers(serializer.data)
                return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
            except IntegrityError as exc:
                if attempt == 0 and 'warehouses_pkey' in str(exc):
                    _reset_warehouse_pk_sequence()
                    serializer = self.get_serializer(data=request.data)
                    serializer.is_valid(raise_exception=True)
                    continue
                raise
