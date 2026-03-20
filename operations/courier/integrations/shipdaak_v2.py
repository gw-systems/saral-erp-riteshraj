"""Shipdaak direct API client (stdlib HTTP client)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

from django.conf import settings
from django.core.cache import cache

from .errors import (
    AuthError,
    InsufficientBalance,
    UpstreamError,
    ValidationError,
    WarehouseNotSynced,
)


def _parse_error_message(payload: Any) -> str:
    if isinstance(payload, dict):
        msg = payload.get("message") or payload.get("detail")
        if not msg and isinstance(payload.get("errors"), dict):
            first_error = next(iter(payload["errors"].values()), None)
            if isinstance(first_error, list) and first_error:
                msg = first_error[0]
            elif first_error:
                msg = first_error
        if msg:
            return str(msg)
    return str(payload)


def _raise_for_error(status_code: int, payload: Any) -> None:
    if 200 <= status_code < 300:
        return

    message = _parse_error_message(payload).lower()
    if status_code in (401, 403):
        raise AuthError(_parse_error_message(payload))
    if status_code == 400:
        if "warehouse" in message and "sync" in message:
            raise WarehouseNotSynced(_parse_error_message(payload))
        raise ValidationError(_parse_error_message(payload))
    if "no credit available" in message or "insufficient" in message:
        raise InsufficientBalance(_parse_error_message(payload))
    if "warehouse" in message and "sync" in message:
        raise WarehouseNotSynced(_parse_error_message(payload))
    raise UpstreamError(_parse_error_message(payload))


def _raise_for_shipdaak_payload_failure(payload: Any) -> None:
    """
    Shipdaak may return HTTP 200 with {"status": false, ...}.
    Treat it as an upstream failure using the same domain errors.
    """
    if not isinstance(payload, dict):
        return

    if payload.get("status") is not False:
        return

    message = _parse_error_message(payload)
    lowered = message.lower()

    if "no credit available" in lowered or "insufficient" in lowered:
        raise InsufficientBalance(message)
    if "warehouse" in lowered and "sync" in lowered:
        raise WarehouseNotSynced(message)
    if "auth" in lowered or "token" in lowered or "unauthorized" in lowered:
        raise AuthError(message)
    raise UpstreamError(message)


def _http_json_request(
    *,
    method: str,
    url: str,
    timeout: int,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    if params:
        query = parse.urlencode(params)
        delimiter = "&" if "?" in url else "?"
        url = f"{url}{delimiter}{query}"

    encoded_body = None
    req_headers = dict(headers or {})
    if body is not None:
        encoded_body = json.dumps(body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = request.Request(url=url, data=encoded_body, method=method.upper(), headers=req_headers)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw) if raw else {}
            except Exception:
                payload = {"message": raw}
            return int(resp.status), payload
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {"message": raw or str(exc)}
        return int(exc.code), payload
    except error.URLError as exc:
        return 503, {"message": f"Connection error: {exc.reason}"}


@dataclass
class ShipdaakAuthTokenProvider:
    """Server-side auth/token cache for direct Shipdaak API."""

    base_url: str
    email: str
    password: str
    timeout_seconds: int

    _CACHE_KEY = "shipdaak_v2_service_token"
    _CACHE_TTL_FALLBACK = 60 * 60 * 12
    _CACHE_EXPIRY_BUFFER = 60

    def get_token(self) -> str:
        cached = cache.get(self._CACHE_KEY)
        if cached:
            return cached
        return self._authenticate()

    def _authenticate(self) -> str:
        if not self.email or not self.password:
            raise AuthError("Shipdaak credentials are not configured.")

        status_code, payload = _http_json_request(
            method="POST",
            url=f"{self.base_url}/v1/auth/token",
            timeout=self.timeout_seconds,
            body={"email": self.email, "password": self.password},
        )
        _raise_for_error(status_code, payload)
        _raise_for_shipdaak_payload_failure(payload)

        token = None
        if isinstance(payload, dict):
            token = payload.get("access_token") or payload.get("token")
        if not token:
            raise AuthError("Shipdaak auth did not return an access token.")

        ttl = self._CACHE_TTL_FALLBACK
        if isinstance(payload, dict):
            for key in ("expires_in", "expires", "expiry"):
                expiry = payload.get(key)
                try:
                    ttl = max(int(expiry) - self._CACHE_EXPIRY_BUFFER, 60)
                    break
                except Exception:
                    continue

        cache.set(self._CACHE_KEY, token, ttl)
        return token


class ShipdaakV2Client:
    """Thin client around direct Shipdaak APIs."""

    def __init__(self) -> None:
        base_url = (
            getattr(settings, "SHIPDAAK_API_BASE_URL", "") or "https://api.shipdaak.com"
        ).rstrip("/")
        if not base_url:
            raise AuthError("SHIPDAAK_API_BASE_URL is not configured.")

        timeout = int(getattr(settings, "SHIPDAAK_TIMEOUT_SECONDS", 30))
        self.base_url = base_url
        self.timeout_seconds = timeout
        self.token_provider = ShipdaakAuthTokenProvider(
            base_url=base_url,
            email=getattr(settings, "SHIPDAAK_EMAIL", ""),
            password=getattr(settings, "SHIPDAAK_PASSWORD", ""),
            timeout_seconds=timeout,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        token = self.token_provider.get_token()
        status_code, payload = _http_json_request(
            method=method,
            url=f"{self.base_url}{path}",
            timeout=self.timeout_seconds,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            body=json_body,
        )
        _raise_for_error(status_code, payload)
        _raise_for_shipdaak_payload_failure(payload)
        return payload

    @staticmethod
    def _unwrap_data(payload: Any) -> Any:
        if isinstance(payload, dict) and "data" in payload:
            return payload.get("data")
        return payload

    @staticmethod
    def _as_number(value: Any) -> float:
        return float(value) if value is not None else 0.0

    @staticmethod
    def _normalize_total_amount(value: Any) -> float:
        """
        Shipdaak requires total_amount >= 1.
        Keep payloads valid even when local order value is missing/zero.
        """
        try:
            amount = float(value)
        except Exception:
            amount = 0.0
        return amount if amount >= 1 else 1.0

    def serviceability(self, **params: Any) -> Any:
        payload: dict[str, Any] = {
            "filterType": params.get("filterType", "rate"),
            "origin": params.get("origin") or params.get("sourcePin"),
            "destination": params.get("destination") or params.get("destinationPin"),
            "paymentType": params.get("paymentType")
            or ("cod" if str(params.get("paymentMethod", "")).upper() == "COD" else "prepaid"),
            "weight": self._as_number(params.get("weight")),
            "length": self._as_number(params.get("length")),
            "breadth": self._as_number(params.get("breadth")),
            "height": self._as_number(params.get("height")),
        }
        if params.get("orderAmount") is not None or params.get("sellingPrice") is not None:
            payload["orderAmount"] = self._as_number(
                params.get("orderAmount", params.get("sellingPrice"))
            )

        raw = self._request(
            "POST",
            "/v1/courier/get-rate-serviceability",
            json_body=payload,
        )
        data = self._unwrap_data(raw)
        if not isinstance(data, list):
            return data
        return sorted(data, key=lambda x: x.get("total_charges", x.get("totalCharges", 0)))

    def create_warehouse(
        self,
        *,
        warehouse_name: str,
        contact_name: str,
        contact_no: str,
        address: str,
        pin_code: str,
        city: str,
        state: str,
        address_2: str | None = None,
        gst_number: str | None = None,
    ) -> Any:
        location_data: dict[str, Any] = {
            "warehouse_name": warehouse_name,
            "contact_name": contact_name,
            "phone": contact_no,
            "address_line_1": address,
            "pincode": pin_code,
            "city": city,
            "state": state,
        }
        if address_2:
            location_data["address_line_2"] = address_2
        if gst_number:
            location_data["gst_number"] = gst_number

        payload = {
            "pickup_location": location_data,
            "rto_location": location_data,
        }

        response = self._request(
            "POST",
            "/v1/warehouse/create-warehouse",
            json_body=payload,
        )
        if isinstance(response, dict):
            data = response.get("data")
            if isinstance(data, dict):
                if "pickupId" not in response and data.get("pickup_warehouse_id") is not None:
                    response["pickupId"] = data.get("pickup_warehouse_id")
                if "rtoId" not in response and data.get("rto_warehouse_id") is not None:
                    response["rtoId"] = data.get("rto_warehouse_id")
        return response

    def create_shipment(
        self,
        *,
        order_id: str,
        courier_id: int,
        weight_kg: float,
        length_cm: float,
        breadth_cm: float,
        height_cm: float,
        pickup_warehouse_id: int,
        rto_warehouse_id: int,
        pay_type: str = "prepaid",
        total_amount: float = 0.0,
        recipient_name: str = "",
        recipient_address: str = "",
        recipient_pincode: str = "",
        recipient_phone: str = "",
        recipient_city: str = "",
        recipient_state: str = "",
        order_items: list[dict[str, Any]] | None = None,
        use_global_account: bool = False,
        label_format: str = "thermal",
    ) -> Any:
        # Kept for request compatibility. Direct Shipdaak mode always uses
        # module-level credentials, so this switch is intentionally ignored.
        _ = use_global_account

        payload = {
            "order_no": order_id,
            "pay_type": pay_type,
            "weight": int(round(float(weight_kg) * 1000)),
            "dimensions": {
                "length": float(length_cm),
                "breadth": float(breadth_cm),
                "height": float(height_cm),
            },
            "total_amount": self._normalize_total_amount(total_amount),
            "courier": int(courier_id),
            "pickup_warehouse": int(pickup_warehouse_id),
            "rto_warehouse": int(rto_warehouse_id),
            "label_format": label_format,
            "is_shipment_created": "yes",
            "consignee": {
                "name": recipient_name,
                "address1": recipient_address,
                "city": recipient_city,
                "state": recipient_state,
                "pincode": str(recipient_pincode),
                "phone": recipient_phone,
            },
            "order_items": order_items or [],
        }
        response = self._request(
            "POST",
            "/v1/shipments/generate-shipment",
            json_body=payload,
        )
        data = self._unwrap_data(response)
        if isinstance(data, dict):
            normalized = dict(data)
            if "label" not in normalized and data.get("label_url"):
                normalized["label"] = data.get("label_url")
            return normalized
        return data

    def track_shipment(self, awb: str) -> Any:
        response = self._request(
            "GET",
            f"/v1/shipments/track-shipment/{awb}",
        )
        return self._unwrap_data(response)

    def cancel_shipment(self, awb: str) -> Any:
        response = self._request(
            "POST",
            "/v1/shipments/cancel-shipment",
            json_body={"awb_number": awb},
        )
        return self._unwrap_data(response)

    def get_label(self, awb: str) -> Any:
        response = self._request(
            "POST",
            "/v1/shipments/bulk-label-shipment",
            json_body={"awb_nos": [awb], "label_format": "thermal"},
        )
        data = self._unwrap_data(response)
        if isinstance(data, dict):
            if "label" not in data and data.get("label_url"):
                data["label"] = data.get("label_url")
        return data

    def generate_bulk_labels(self, awb_numbers: list[str], label_format: str = "thermal") -> Any:
        response = self._request(
            "POST",
            "/v1/shipments/bulk-label-shipment",
            json_body={"awb_nos": awb_numbers, "label_format": label_format},
        )
        data = self._unwrap_data(response)
        if isinstance(data, dict):
            if "label" not in data and data.get("label_url"):
                data["label"] = data.get("label_url")
        return data

    def get_couriers(self) -> Any:
        response = self._request(
            "GET",
            "/v1/courier/get-courier",
        )
        return self._unwrap_data(response)

    def register_order(
        self,
        *,
        order_no: str,
        pay_type: str,          # 'cod' or 'prepaid'
        weight_grams: int,      # weight in grams
        length_cm: float,
        breadth_cm: float,
        height_cm: float,
        recipient_name: str,
        recipient_address: str,
        recipient_pincode: str,
        recipient_phone: str,
        recipient_city: str = "",
        recipient_state: str = "",
        total_amount: float = 0.0,
        order_items: list | None = None,
        pickup_warehouse_id: int | None = None,
        rto_warehouse_id: int | None = None,
    ) -> Any:
        """
        Register an order in ShipDaak's Orders tab (no AWB generated yet).

        ShipDaak will show this order so the operator can select courier /
        warehouse and issue an AWB from within ShipDaak.

        Returns a dict containing ShipDaak's ``orderId`` (int) and
        ``orderStatus`` (e.g. "New").
        """
        normalized_order_items = order_items or [
            {
                "name": "Item",
                "quantity": 1,
                "price": self._normalize_total_amount(total_amount),
            }
        ]
        payload: dict[str, Any] = {
            "order_no": order_no,
            "pay_type": pay_type,
            "weight": weight_grams,
            "dimensions": {
                "length": length_cm,
                "breadth": breadth_cm,
                "height": height_cm,
            },
            "total_amount": self._normalize_total_amount(total_amount),
            "label_format": "thermal",
            "is_shipment_created": "no",
            "consignee": {
                "name": recipient_name,
                "address1": recipient_address,
                "city": recipient_city,
                "state": recipient_state,
                "pincode": str(recipient_pincode),
                "phone": recipient_phone,
            },
            "order_items": normalized_order_items,
        }
        if pickup_warehouse_id is not None:
            payload["pickup_warehouse"] = int(pickup_warehouse_id)
        if rto_warehouse_id is not None:
            payload["rto_warehouse"] = int(rto_warehouse_id)
        response = self._request(
            "POST",
            "/v1/shipments/generate-shipment",
            json_body=payload,
        )
        if isinstance(response, dict):
            data = response.get("data")
            if isinstance(data, dict):
                order_id = data.get("orderId") or data.get("order_id")
                if order_id is not None and "orderId" not in response:
                    response["orderId"] = order_id
        return response

    def generate_manifest(self, awb_numbers: list[str]) -> Any:
        response = self._request(
            "POST",
            "/v1/shipments/bulk-manifest-shipment",
            json_body={"awb_nos": awb_numbers},
        )
        return self._unwrap_data(response)

    def sync_warehouse(self, warehouse_id: int, gst_number: str | None = None) -> Any:
        _ = warehouse_id
        _ = gst_number
        raise ValidationError(
            "Direct Shipdaak API does not support courier warehouse sync by local courier warehouse ID. "
            "Use create_warehouse() with full courier warehouse details."
        )

    def warehouse_status(self, warehouse_id: int) -> Any:
        _ = warehouse_id
        raise ValidationError(
            "Direct Shipdaak API does not expose courier warehouse status by local courier warehouse ID. "
            "Use locally stored courier warehouse sync fields instead."
        )


# Backward-compatible alias for old imports in tests and callsites.
WMSAuthTokenProvider = ShipdaakAuthTokenProvider
