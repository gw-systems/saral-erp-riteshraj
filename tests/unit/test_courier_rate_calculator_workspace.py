import json

import pytest
from django.db import connection
from django.test import override_settings
from django.urls import reverse
from django.http import JsonResponse

from operations.courier.models import Warehouse
from operations import views_porter_invoice

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
    assert "B2C Orders" in content
    assert "Create Order" in content
    assert "Book AWB" in content
    assert "Create FTL Order" in content


@override_settings(**WORKSPACE_TEST_SETTINGS)
def test_courier_shipments_workspace_renders_native_controls(client, admin_user):
    client.force_login(admin_user)

    response = client.get(reverse("operations:courier:shipments-dashboard"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Shipment Control" in content
    assert "Carrier Comparison" in content
    assert "Book Selected Carrier" not in content
    assert "FTL Booking Queue" in content


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


