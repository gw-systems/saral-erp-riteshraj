import json

from django.test import override_settings
from django.urls import reverse


WORKSPACE_TEST_SETTINGS = {
    "ALLOWED_HOSTS": ["testserver", "localhost", "127.0.0.1"],
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
}

@override_settings(**WORKSPACE_TEST_SETTINGS)
def test_courier_rate_calculator_page_renders_parity_ui(client, admin_user):
    client.force_login(admin_user)

    response = client.get(reverse("operations:courier:rate-calculator"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "B2C (&lt; 20kg)" in content
    assert "B2B (&gt;= 20kg)" in content
    assert "FTL Rate" in content
    assert "Rate Shipment Calculator v2" in content
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


