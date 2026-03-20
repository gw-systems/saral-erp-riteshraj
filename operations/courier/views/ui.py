"""ERP-native courier workspace views."""

from urllib.parse import quote

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import redirect, render
from django.urls import reverse

from ..models import Courier, Order, OrderStatus, Warehouse
from ..permissions import user_can_manage_courier, user_can_operate_courier


SECTION_META = {
    "dashboard": {
        "title": "Courier Dashboard",
        "subtitle": "Monitor carriers, orders, live shipments, and warehouse readiness in one place.",
    },
    "calculator": {
        "title": "Rate Calculator",
        "subtitle": "Compare courier rates inside the ERP using the live courier engine.",
    },
    "orders": {
        "title": "Courier Orders",
        "subtitle": "Create draft orders, compare carriers, and book shipments from the same workspace.",
    },
    "shipments": {
        "title": "Shipment Control",
        "subtitle": "Track booked shipments, sync statuses, and fetch labels without leaving the ERP.",
    },
    "warehouses": {
        "title": "Courier Warehouses",
        "subtitle": "Manage courier-only warehouses and keep Shipdaak pickup and RTO IDs synced.",
    },
}


def _ensure_courier_access(request) -> None:
    if not user_can_operate_courier(getattr(request, "user", None)):
        raise PermissionDenied("Courier workspace access is not available for this user.")


def _status_breakdown():
    labels = dict(OrderStatus.choices)
    rows = (
        Order.objects.values("status")
        .annotate(total=Count("id"))
        .order_by("-total", "status")
    )
    return [
        {
            "value": row["status"],
            "label": labels.get(row["status"], row["status"]),
            "total": row["total"],
        }
        for row in rows
    ]


def _workspace_context(request, active_section: str) -> dict:
    meta = SECTION_META[active_section]
    shipment_statuses = [
        OrderStatus.BOOKED,
        OrderStatus.MANIFESTED,
        OrderStatus.PICKED_UP,
        OrderStatus.OUT_FOR_DELIVERY,
        OrderStatus.NDR,
        OrderStatus.RTO,
        OrderStatus.PICKUP_EXCEPTION,
    ]
    recent_orders = (
        Order.objects.select_related("carrier", "warehouse")
        .order_by("-created_at")[:8]
    )
    recent_shipments = (
        Order.objects.select_related("carrier", "warehouse")
        .exclude(status=OrderStatus.DRAFT)
        .order_by("-updated_at")[:8]
    )
    return {
        "active_section": active_section,
        "section_title": meta["title"],
        "section_subtitle": meta["subtitle"],
        "can_manage_courier": user_can_manage_courier(getattr(request, "user", None)),
        "workspace_stats": {
            "total_carriers": Courier.objects.count(),
            "active_carriers": Courier.objects.filter(is_active=True).count(),
            "total_orders": Order.objects.count(),
            "draft_orders": Order.objects.filter(status=OrderStatus.DRAFT).count(),
            "live_shipments": Order.objects.filter(status__in=shipment_statuses).count(),
            "delivered_orders": Order.objects.filter(status=OrderStatus.DELIVERED).count(),
            "warehouses": Warehouse.objects.count(),
            "synced_warehouses": Warehouse.objects.filter(
                shipdaak_pickup_id__isnull=False,
                shipdaak_rto_id__isnull=False,
            ).count(),
        },
        "status_breakdown": _status_breakdown(),
        "recent_orders": recent_orders,
        "recent_shipments": recent_shipments,
        "direct_admin_urls": {
            "carriers": f"{reverse('admin:courier_courier_changelist')}?admin=1",
            "orders": f"{reverse('admin:courier_order_changelist')}?admin=1",
            "warehouses": f"{reverse('admin:courier_warehouse_changelist')}?admin=1",
        },
    }


def _render_workspace(request, active_section: str):
    _ensure_courier_access(request)
    return render(request, "courier/workspace_native.html", _workspace_context(request, active_section))


def login_view(request):
    target = request.GET.get("next") or reverse("operations:courier:dashboard")
    login_url = reverse("accounts:login")
    return redirect(f"{login_url}?next={quote(target, safe='/?:=&')}")


def root_redirect(request):
    if not getattr(request.user, "is_authenticated", False):
        return login_view(request)
    return redirect("operations:courier:dashboard")


@login_required
def dashboard_view(request):
    return _render_workspace(request, "dashboard")


@login_required
def rate_calculator_view(request):
    return _render_workspace(request, "calculator")


@login_required
def orders_dashboard_view(request):
    return _render_workspace(request, "orders")


@login_required
def shipments_dashboard_view(request):
    return _render_workspace(request, "shipments")


@login_required
def warehouses_dashboard_view(request):
    return _render_workspace(request, "warehouses")


