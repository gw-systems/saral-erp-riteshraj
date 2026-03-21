"""ERP-native courier workspace views."""

from urllib.parse import quote

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from ..models import Courier, FTLOrder, Order, OrderStatus, Warehouse
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

ORDER_FILTERS = {"all", "draft", "booked", "manifested", "cancelled"}
ORDER_TYPES = {"b2c", "b2b", "ftl"}


def _order_type_for_instance(order: Order) -> str:
    carrier_type = getattr(getattr(order, "carrier", None), "carrier_type", "") or ""
    carrier_type = carrier_type.strip().lower()
    if carrier_type in {"b2b", "b2c"}:
        return carrier_type
    weight = order.applicable_weight or order.weight or 0
    return "b2b" if weight >= 20 else "b2c"


def _normalize_order_type(raw_value: str | None, *, allow_ftl: bool = True) -> str:
    allowed = ORDER_TYPES if allow_ftl else {"b2c", "b2b"}
    value = (raw_value or "").strip().lower()
    return value if value in allowed else "b2c"


def _normalize_order_status(raw_value: str | None) -> str:
    value = (raw_value or "").strip().lower()
    return value if value in ORDER_FILTERS else "all"


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
        "initial_order_type": _normalize_order_type(request.GET.get("type")),
        "initial_order_status": _normalize_order_status(request.GET.get("status")),
        "initial_shipment_type": _normalize_order_type(request.GET.get("type")),
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


def _order_form_context(request, *, order_type: str, order: Order | None = None) -> dict:
    is_edit = order is not None
    resolved_type = _normalize_order_type(order_type, allow_ftl=False)
    title_prefix = "Edit" if is_edit else "Create"
    title_suffix = "B2B Order" if resolved_type == "b2b" else "B2C Order"
    return {
        "active_section": "orders",
        "form_mode": "edit" if is_edit else "create",
        "form_title": f"{title_prefix} {title_suffix}",
        "form_subtitle": "Keep long courier workflows on a full page so every field stays accessible on laptop screens.",
        "order_type": resolved_type,
        "order": order,
        "is_edit": is_edit,
        "warehouses": Warehouse.objects.filter(is_active=True).order_by("name"),
        "back_url": f"{reverse('operations:courier:orders-dashboard')}?type={resolved_type}",
    }


def _ftl_form_context(request, *, order: FTLOrder | None = None) -> dict:
    is_edit = order is not None
    return {
        "active_section": "orders",
        "form_mode": "edit" if is_edit else "create",
        "form_title": "Edit FTL Order" if is_edit else "Create FTL Order",
        "form_subtitle": "Route selection, pricing preview, and booking details stay on one page instead of a constrained drawer.",
        "order": order,
        "is_edit": is_edit,
        "back_url": f"{reverse('operations:courier:orders-dashboard')}?type=ftl",
    }


@login_required
def order_create_view(request, order_type: str):
    _ensure_courier_access(request)
    context = _order_form_context(request, order_type=order_type)
    return render(request, "courier/order_form_page.html", context)


@login_required
def order_edit_view(request, pk: int):
    _ensure_courier_access(request)
    order = get_object_or_404(Order.objects.select_related("warehouse", "carrier"), pk=pk)
    if order.status != OrderStatus.DRAFT:
        raise PermissionDenied("Only draft courier orders can be edited.")
    context = _order_form_context(request, order_type=_order_type_for_instance(order), order=order)
    return render(request, "courier/order_form_page.html", context)


@login_required
def ftl_order_create_view(request):
    _ensure_courier_access(request)
    return render(request, "courier/ftl_order_form_page.html", _ftl_form_context(request))


@login_required
def ftl_order_edit_view(request, pk: int):
    _ensure_courier_access(request)
    order = get_object_or_404(FTLOrder, pk=pk)
    if order.status != OrderStatus.DRAFT:
        raise PermissionDenied("Only draft FTL orders can be edited.")
    return render(request, "courier/ftl_order_form_page.html", _ftl_form_context(request, order=order))


