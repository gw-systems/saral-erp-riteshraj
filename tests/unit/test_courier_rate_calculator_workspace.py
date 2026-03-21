import json
import importlib
import sys
import types
from decimal import Decimal

import pytest
from django.db import connection
from django.test import override_settings
from django.urls import reverse
from django.http import JsonResponse

from operations.courier.models import FTLOrder, Order, Warehouse
from operations import views_porter_invoice


def _install_google_ads_stubs():
    try:
        importlib.import_module("google")
    except ImportError:
        sys.modules.setdefault("google", types.ModuleType("google"))

    if "google.ads.googleads.client" not in sys.modules:
        google_module = sys.modules["google"]

        ads_module = sys.modules.setdefault("google.ads", types.ModuleType("google.ads"))
        google_module.ads = ads_module

        googleads_module = sys.modules.setdefault("google.ads.googleads", types.ModuleType("google.ads.googleads"))
        ads_module.googleads = googleads_module

        client_module = sys.modules.setdefault("google.ads.googleads.client", types.ModuleType("google.ads.googleads.client"))
        errors_module = sys.modules.setdefault("google.ads.googleads.errors", types.ModuleType("google.ads.googleads.errors"))
        googleads_module.client = client_module
        googleads_module.errors = errors_module

        class DummyGoogleAdsClient:
            @staticmethod
            def load_from_dict(config):
                return types.SimpleNamespace(config=config, get_service=lambda name: types.SimpleNamespace(search=lambda **kwargs: []))

        class DummyGoogleAdsException(Exception):
            def __init__(self, *args, **kwargs):
                super().__init__(*args)
                self.failure = types.SimpleNamespace(errors=[])

        client_module.GoogleAdsClient = DummyGoogleAdsClient
        errors_module.GoogleAdsException = DummyGoogleAdsException

    try:
        importlib.import_module("google.oauth2.credentials")
    except ImportError:
        google_module = sys.modules["google"]
        oauth2_module = sys.modules.setdefault("google.oauth2", types.ModuleType("google.oauth2"))
        credentials_module = sys.modules.setdefault("google.oauth2.credentials", types.ModuleType("google.oauth2.credentials"))
        google_module.oauth2 = oauth2_module
        oauth2_module.credentials = credentials_module

        class DummyCredentials:
            def __init__(self, **kwargs):
                self.token = kwargs.get("token")
                self.refresh_token = kwargs.get("refresh_token")
                self.token_uri = kwargs.get("token_uri")
                self.client_id = kwargs.get("client_id")
                self.client_secret = kwargs.get("client_secret")
                self.scopes = kwargs.get("scopes")
                self.expiry = kwargs.get("expiry")

            def refresh(self, request):
                _ = request

        credentials_module.Credentials = DummyCredentials

    try:
        importlib.import_module("google.auth.transport.requests")
    except ImportError:
        google_module = sys.modules["google"]
        auth_module = sys.modules.setdefault("google.auth", types.ModuleType("google.auth"))
        transport_module = sys.modules.setdefault("google.auth.transport", types.ModuleType("google.auth.transport"))
        requests_module = sys.modules.setdefault("google.auth.transport.requests", types.ModuleType("google.auth.transport.requests"))
        google_module.auth = auth_module
        auth_module.transport = transport_module
        transport_module.requests = requests_module

        class DummyRequest:
            pass

        requests_module.Request = DummyRequest

    if "google_auth_oauthlib.flow" not in sys.modules:
        google_auth_oauthlib_module = sys.modules.setdefault("google_auth_oauthlib", types.ModuleType("google_auth_oauthlib"))
        flow_module = sys.modules.setdefault("google_auth_oauthlib.flow", types.ModuleType("google_auth_oauthlib.flow"))
        google_auth_oauthlib_module.flow = flow_module

        class DummyFlow:
            credentials = types.SimpleNamespace(
                token="token",
                refresh_token="refresh",
                token_uri="https://oauth2.googleapis.com/token",
                client_id="client-id",
                client_secret="client-secret",
                scopes=[],
                expiry=None,
            )

            @classmethod
            def from_client_config(cls, *args, **kwargs):
                _ = args, kwargs
                return cls()

            def authorization_url(self, **kwargs):
                _ = kwargs
                return ("https://example.com/auth", "state-token")

            def fetch_token(self, **kwargs):
                _ = kwargs

        flow_module.Flow = DummyFlow


_install_google_ads_stubs()

WORKSPACE_TEST_SETTINGS = {
    "ALLOWED_HOSTS": ["testserver", "localhost", "127.0.0.1"],
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
}


def _make_warehouse(**overrides):
    next_id = (Warehouse.objects.order_by("-id").values_list("id", flat=True).first() or 0) + 1
    payload = {
        "id": next_id,
        "name": "Primary Warehouse",
        "contact_name": "Ops User",
        "contact_no": "9876543210",
        "address": "Warehouse Lane",
        "address_2": "",
        "pincode": "400001",
        "city": "Mumbai",
        "state": "Maharashtra",
        "gst_number": "27ABCDE1234F1Z5",
    }
    payload.update(overrides)
    return Warehouse.objects.create(**payload)


def _make_order(**overrides):
    next_number = Order.objects.count() + 1
    payload = {
        "order_number": f"ORD-{next_number:05d}",
        "recipient_name": "Demo Recipient",
        "recipient_contact": "9876543210",
        "recipient_address": "Courier Street",
        "recipient_pincode": 400001,
        "recipient_city": "Mumbai",
        "recipient_state": "Maharashtra",
        "recipient_email": "demo@example.com",
        "sender_pincode": 400002,
        "sender_name": "Primary Warehouse",
        "sender_address": "Warehouse Lane",
        "sender_phone": "9123456789",
        "weight": 1.5,
        "length": 10,
        "width": 12,
        "height": 8,
        "payment_mode": "prepaid",
        "order_value": Decimal("0.00"),
        "item_type": "Shirt",
        "sku": "SKU-1",
        "quantity": 1,
        "item_amount": Decimal("0.00"),
        "status": "draft",
    }
    payload.update(overrides)
    return Order.objects.create(**payload)


def _make_ftl_order(**overrides):
    next_number = FTLOrder.objects.count() + 1
    payload = {
        "order_number": f"FTL-{next_number:05d}",
        "name": "FTL Customer",
        "email": "ftl@example.com",
        "phone": "9876543210",
        "source_city": "Mumbai",
        "source_address": "Source Lane",
        "source_pincode": 400001,
        "destination_city": "Delhi",
        "destination_address": "Destination Lane",
        "destination_pincode": 110001,
        "container_type": "20FT",
        "base_price": Decimal("10000.00"),
        "escalation_amount": Decimal("1500.00"),
        "price_with_escalation": Decimal("11500.00"),
        "gst_amount": Decimal("2070.00"),
        "total_price": Decimal("13570.00"),
        "status": "draft",
    }
    payload.update(overrides)
    return FTLOrder.objects.create(**payload)


@pytest.fixture(autouse=True)
def _stub_missing_porter_invoice_views(monkeypatch):
    def _placeholder(*args, **kwargs):
        return JsonResponse({"detail": "stubbed during courier workspace tests"})

    for attr in (
        "porter_invoice_edit_upload_api",
        "porter_invoice_drive_subfolders_api",
        "porter_invoice_drive_upload_batch_api",
    ):
        if not hasattr(views_porter_invoice, attr):
            monkeypatch.setattr(views_porter_invoice, attr, _placeholder, raising=False)


@override_settings(**WORKSPACE_TEST_SETTINGS)
def test_courier_rate_calculator_page_renders_parity_ui(client, admin_user):
    client.force_login(admin_user)

    response = client.get(reverse("operations:courier:rate-calculator"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "B2C (&lt; 20kg)" in content
    assert "B2B (&gt;= 20kg)" in content
    assert "FTL Rate" in content
    assert "Rate Shipment Calculator" in content
    assert "Rate Shipment Calculator v2" not in content
    assert "Add Another Box" in content
    assert "B2C Rate Card" in content


def test_compare_rates_requires_authenticated_courier_access(client):
    response = client.post(
        reverse("operations:courier:compare-rates"),
        data=json.dumps(
            {
                "source_pincode": 400001,
                "dest_pincode": 110001,
                "orders": [{"weight": 1.0, "length": 10, "width": 10, "height": 10}],
                "mode": "Both",
                "is_cod": False,
                "order_value": 0,
                "business_type": "b2c",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code in {401, 403}


def test_compare_rates_allows_logged_in_operator_and_returns_service_category(client, admin_user, monkeypatch):
    client.force_login(admin_user)

    monkeypatch.setattr("operations.courier.views.public.get_zone_column", lambda source, dest: ("z_a", "Metro"))
    monkeypatch.setattr(
        "operations.courier.views.public.load_rates",
        lambda: [
            {
                "id": 1,
                "active": True,
                "carrier_name": "Demo Air Carrier",
                "mode": "Air",
                "service_category": "Air",
            }
        ],
    )
    monkeypatch.setattr(
        "operations.courier.views.public.calculate_cost",
        lambda **kwargs: {
            "carrier": "Demo Air Carrier",
            "zone": "Metro",
            "total_cost": 125.5,
            "breakdown": {"base_freight": 100, "gst_amount": 19.08, "final_total": 125.5},
            "serviceable": True,
        },
    )

    response = client.post(
        reverse("operations:courier:compare-rates"),
        data=json.dumps(
            {
                "source_pincode": 400001,
                "dest_pincode": 110001,
                "orders": [{"weight": 1.0, "length": 10, "width": 10, "height": 10}],
                "mode": "Both",
                "is_cod": False,
                "order_value": 0,
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    body = response.json()
    assert body[0]["carrier"] == "Demo Air Carrier"
    assert body[0]["service_category"] == "Air"


def test_ftl_routes_require_authenticated_courier_access(client):
    response = client.get(reverse("operations:courier:get-ftl-routes"))

    assert response.status_code in {401, 403}


def test_ftl_routes_allow_logged_in_operator(client, admin_user, monkeypatch):
    client.force_login(admin_user)
    monkeypatch.setattr(
        "operations.courier.views.ftl.load_ftl_rates",
        lambda: {"Mumbai": {"Delhi": {"20ft": 12000.0}}},
    )

    response = client.get(reverse("operations:courier:get-ftl-routes"))

    assert response.status_code == 200
    assert response.json() == {"Mumbai": {"Delhi": ["20ft"]}}


def test_b2c_rate_card_options_require_authenticated_courier_access(client):
    response = client.get(reverse("operations:courier:b2c-rate-card-options"))

    assert response.status_code in {401, 403}


def test_b2c_rate_card_options_allow_logged_in_operator(client, admin_user):
    client.force_login(admin_user)

    response = client.get(reverse("operations:courier:b2c-rate-card-options"))

    assert response.status_code == 200
    body = response.json()
    assert "carriers" in body
    assert "total" in body

@override_settings(**WORKSPACE_TEST_SETTINGS)
def test_courier_orders_workspace_renders_native_controls(client, admin_user):
    client.force_login(admin_user)

    response = client.get(reverse("operations:courier:orders-dashboard"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Courier Orders" in content
    assert "Create B2C Order" in content
    assert "Drafts And Live Orders" in content
    assert "FTL Draft Queue" in content
    assert "Book AWB" in content


@override_settings(**WORKSPACE_TEST_SETTINGS)
def test_courier_shipments_workspace_renders_native_controls(client, admin_user):
    client.force_login(admin_user)

    response = client.get(reverse("operations:courier:shipments-dashboard"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Shipment Booking" in content
    assert "Carrier Comparison" in content
    assert "Book Selected Carrier" not in content
    assert "FTL Booking Queue" in content
    assert "Use Godamwale Global Account" in content


@override_settings(**WORKSPACE_TEST_SETTINGS)
def test_courier_order_create_page_renders_full_page_form(client, admin_user):
    client.force_login(admin_user)

    response = client.get(reverse("operations:courier:order-create", args=["b2c"]))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Create B2C Order" in content
    assert "Recipient Details" in content
    assert "Commercial Details" in content


@override_settings(**WORKSPACE_TEST_SETTINGS)
def test_courier_order_edit_page_renders_full_page_form(client, admin_user):
    client.force_login(admin_user)
    order = _make_order()

    response = client.get(reverse("operations:courier:order-edit", args=[order.id]))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Edit B2C Order" in content
    assert "Recipient Details" in content
    assert f'apiUrl: "/operations/courier/orders/{order.id}/"' in content


@override_settings(**WORKSPACE_TEST_SETTINGS)
def test_courier_ftl_order_create_page_renders_full_page_form(client, admin_user):
    client.force_login(admin_user)

    response = client.get(reverse("operations:courier:ftl-order-create"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Create FTL Order" in content
    assert "Route & Shipment" in content
    assert "Pricing Preview" in content


@override_settings(**WORKSPACE_TEST_SETTINGS)
def test_courier_ftl_order_edit_page_renders_full_page_form(client, admin_user):
    client.force_login(admin_user)
    order = _make_ftl_order()

    response = client.get(reverse("operations:courier:ftl-order-edit", args=[order.id]))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Edit FTL Order" in content
    assert "Pricing Preview" in content
    assert f'apiUrl: "/operations/courier/ftl-orders/{order.id}/"' in content


@override_settings(**WORKSPACE_TEST_SETTINGS)
def test_courier_warehouses_workspace_renders_native_controls(client, admin_user):
    client.force_login(admin_user)

    response = client.get(reverse("operations:courier:warehouses-dashboard"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Warehouse Readiness" in content
    assert "Warehouse Operations" in content
    assert "Add Warehouse" in content
    assert "Linked To ShipDaak" in content
    assert "Create a brand-new ShipDaak warehouse only when it does not already exist there" in content
    assert "Link Existing ShipDaak IDs" in content


def test_courier_order_and_warehouse_apis_require_authenticated_operator(client):
    order_response = client.get(reverse("operations:courier:order-list"))
    warehouse_response = client.get(reverse("operations:courier:warehouse-list"))

    assert order_response.status_code in {401, 403}
    assert warehouse_response.status_code in {401, 403}


def test_courier_order_and_warehouse_apis_allow_logged_in_operator(client, admin_user):
    client.force_login(admin_user)

    order_response = client.get(reverse("operations:courier:order-list"))
    warehouse_response = client.get(reverse("operations:courier:warehouse-list"))

    assert order_response.status_code == 200
    assert warehouse_response.status_code == 200


def test_courier_warehouse_create_recovers_from_sequence_drift(client, admin_user):
    client.force_login(admin_user)
    _make_warehouse(name="Existing Warehouse 1")
    _make_warehouse(name="Existing Warehouse 2")

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_get_serial_sequence('warehouses', 'id')")
        sequence_name = cursor.fetchone()[0]
        cursor.execute("SELECT setval(%s, %s, true)", [sequence_name, 1])

    response = client.post(
        reverse("operations:courier:warehouse-list"),
        data=json.dumps(
            {
                "name": "Retry Warehouse",
                "contact_name": "Ops User",
                "contact_no": "9876543210",
                "address": "Warehouse Lane",
                "address_2": "",
                "pincode": "400001",
                "city": "Mumbai",
                "state": "Maharashtra",
                "gst_number": "27ABCDE1234F1Z5",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 201, response.content
    assert Warehouse.objects.filter(name="Retry Warehouse").exists()


def test_courier_order_create_allows_multiline_recipient_address(client, admin_user):
    client.force_login(admin_user)

    response = client.post(
        reverse("operations:courier:order-list"),
        data=json.dumps(
            {
                "recipient_name": "D'Souza",
                "recipient_contact": "9876543210",
                "recipient_address": "Flat 5B, Sunrise Apartments\nMG Road",
                "recipient_pincode": 400001,
                "recipient_city": "Mumbai",
                "recipient_state": "Maharashtra",
                "recipient_email": "customer@example.com",
                "sender_pincode": 400002,
                "sender_name": "Primary Warehouse",
                "sender_address": "Warehouse Lane",
                "sender_phone": "9123456789",
                "weight": 1.5,
                "length": 10,
                "width": 12,
                "height": 8,
                "payment_mode": "prepaid",
                "order_value": 0,
                "item_type": "Shirt",
                "sku": "SKU-1",
                "quantity": 1,
                "item_amount": 0,
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["recipient_name"] == "D'Souza"
    assert body["recipient_address"] == "Flat 5B, Sunrise Apartments\nMG Road"


def test_shipdaak_sync_warehouse_reuses_existing_ids_without_create_call(client, admin_user, monkeypatch):
    client.force_login(admin_user)
    warehouse = _make_warehouse(
        shipdaak_pickup_id=111,
        shipdaak_rto_id=222,
    )

    def fail_create(*args, **kwargs):
        raise AssertionError("create_warehouse should not be called for an already linked warehouse")

    monkeypatch.setattr(
        "operations.courier.services.ShipdaakV2Client.create_warehouse",
        fail_create,
    )

    response = client.post(
        reverse("operations:courier:shipdaak-warehouse-sync", args=[warehouse.id]),
        data=json.dumps({}),
        content_type="application/json",
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["alreadyExisted"] is True
    assert body["pickupId"] == 111
    assert body["rtoId"] == 222


def test_shipdaak_import_existing_warehouse_reuses_existing_ids_without_force(client, admin_user, monkeypatch):
    client.force_login(admin_user)
    warehouse = _make_warehouse(
        name="Existing Warehouse",
        shipdaak_pickup_id=333,
        shipdaak_rto_id=444,
    )

    def fail_create(*args, **kwargs):
        raise AssertionError("legacy endpoint must not recreate a linked warehouse unless forced")

    monkeypatch.setattr(
        "operations.courier.services.ShipdaakV2Client.create_warehouse",
        fail_create,
    )

    response = client.post(
        reverse("operations:courier:shipdaak-warehouse-import-existing", args=[warehouse.id]),
        data=json.dumps({}),
        content_type="application/json",
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["alreadyExisted"] is True
    assert body["pickupId"] == 333
    assert body["rtoId"] == 444


def test_shipdaak_import_existing_warehouse_force_allows_recreate(client, admin_user, monkeypatch):
    client.force_login(admin_user)
    warehouse = _make_warehouse(
        name="Force Warehouse",
        shipdaak_pickup_id=101,
        shipdaak_rto_id=202,
    )
    calls = []

    def fake_create(self, **kwargs):
        calls.append(kwargs)
        return {"pickupId": 555, "rtoId": 666}

    monkeypatch.setattr(
        "operations.courier.services.ShipdaakV2Client.create_warehouse",
        fake_create,
    )

    response = client.post(
        reverse("operations:courier:shipdaak-warehouse-import-existing", args=[warehouse.id]),
        data=json.dumps({"force": True}),
        content_type="application/json",
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["alreadyExisted"] is False
    assert body["pickupId"] == 555
    assert body["rtoId"] == 666
    warehouse.refresh_from_db()
    assert warehouse.shipdaak_pickup_id == 555
    assert warehouse.shipdaak_rto_id == 666
    assert len(calls) == 1


def test_shipdaak_link_existing_ids_only_updates_local_ids(client, admin_user, monkeypatch):
    client.force_login(admin_user)
    warehouse = _make_warehouse(name="Manual Link Warehouse")

    def fail_create(*args, **kwargs):
        raise AssertionError("manual linking must not create a ShipDaak warehouse")

    monkeypatch.setattr(
        "operations.courier.services.ShipdaakV2Client.create_warehouse",
        fail_create,
    )

    response = client.post(
        reverse("operations:courier:shipdaak-warehouse-link-existing", args=[warehouse.id]),
        data=json.dumps({"shipdaak_warehouse_id": 777, "rto_id": 888}),
        content_type="application/json",
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["linked"] is True
    assert body["pickupId"] == 777
    assert body["rtoId"] == 888
    warehouse.refresh_from_db()
    assert warehouse.shipdaak_pickup_id == 777
    assert warehouse.shipdaak_rto_id == 888


def test_shipdaak_sync_warehouse_creates_new_link_for_unlinked_warehouse(client, admin_user, monkeypatch):
    client.force_login(admin_user)
    warehouse = _make_warehouse(name="Fresh Warehouse")
    calls = []

    def fake_create(self, **kwargs):
        calls.append(kwargs)
        return {"pickupId": 909, "rtoId": 1001}

    monkeypatch.setattr(
        "operations.courier.services.ShipdaakV2Client.create_warehouse",
        fake_create,
    )

    response = client.post(
        reverse("operations:courier:shipdaak-warehouse-sync", args=[warehouse.id]),
        data=json.dumps({}),
        content_type="application/json",
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["alreadyExisted"] is False
    assert body["pickupId"] == 909
    assert body["rtoId"] == 1001
    warehouse.refresh_from_db()
    assert warehouse.shipdaak_pickup_id == 909
    assert warehouse.shipdaak_rto_id == 1001
    assert len(calls) == 1


@override_settings(
    **WORKSPACE_TEST_SETTINGS,
    SHIPDAAK_ENABLE_BOOKING=True,
    SHIPDAAK_REGISTER_ON_CREATE=True,
)
def test_order_create_reuses_linked_warehouse_ids_without_recreating_shipdaak_warehouse(client, admin_user, monkeypatch):
    client.force_login(admin_user)
    warehouse = _make_warehouse(
        shipdaak_pickup_id=1212,
        shipdaak_rto_id=3434,
    )

    def fail_create(*args, **kwargs):
        raise AssertionError("order creation should reuse linked ShipDaak IDs instead of recreating the warehouse")

    monkeypatch.setattr(
        "operations.courier.services.ShipdaakV2Client.create_warehouse",
        fail_create,
    )

    captured = {}

    def fake_register(self, **kwargs):
        captured.update(kwargs)
        return {"orderId": 9191}

    monkeypatch.setattr(
        "operations.courier.integrations.ShipdaakV2Client.register_order",
        fake_register,
    )

    response = client.post(
        reverse("operations:courier:order-list"),
        data=json.dumps(
            {
                "warehouse": warehouse.id,
                "recipient_name": "Reuse Test",
                "recipient_contact": "9876543210",
                "recipient_address": "Test Address",
                "recipient_pincode": 400001,
                "recipient_city": "Mumbai",
                "recipient_state": "Maharashtra",
                "recipient_email": "reuse@example.com",
                "sender_pincode": 400002,
                "sender_name": "Primary Warehouse",
                "sender_address": "Warehouse Lane",
                "sender_phone": "9123456789",
                "weight": 1.5,
                "length": 10,
                "width": 12,
                "height": 8,
                "payment_mode": "prepaid",
                "order_value": 0,
                "item_type": "Shirt",
                "sku": "SKU-1",
                "quantity": 1,
                "item_amount": 0,
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 201, response.json()
    assert captured["pickup_warehouse_id"] == 1212
    assert captured["rto_warehouse_id"] == 3434


