from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.integrations.xianguanjia.errors import (
    XianGuanJiaError,
    XianGuanJiaErrorType,
    XianGuanJiaNonRetryableError,
    XianGuanJiaRetryableError,
    _is_timeout_error,
    _is_transport_error,
    _map_http_status_to_type,
    _normalize_error_code,
    _normalize_error_type,
    is_retryable_error,
    map_error,
)
from src.integrations.xianguanjia.signing import (
    _body_md5,
    sign_open_platform_request,
    verify_open_platform_callback_signature,
)


class TestNormalizeErrorType:
    def test_none(self):
        assert _normalize_error_type(None) is None

    def test_already_enum(self):
        assert _normalize_error_type(XianGuanJiaErrorType.TIMEOUT) == XianGuanJiaErrorType.TIMEOUT

    def test_empty_string(self):
        assert _normalize_error_type("") is None

    def test_valid_string(self):
        assert _normalize_error_type("TIMEOUT") == XianGuanJiaErrorType.TIMEOUT

    def test_unknown_string(self):
        assert _normalize_error_type("INVALID_TYPE") == XianGuanJiaErrorType.UNKNOWN


class TestNormalizeErrorCode:
    def test_none(self):
        assert _normalize_error_code(None) is None

    def test_empty_string(self):
        assert _normalize_error_code("") is None

    def test_known_retryable(self):
        result = _normalize_error_code("E429")
        assert result is not None
        assert result[0] == XianGuanJiaErrorType.RATE_LIMITED
        assert result[1] is True

    def test_known_non_retryable(self):
        result = _normalize_error_code("E401")
        assert result is not None
        assert result[0] == XianGuanJiaErrorType.AUTH_INVALID
        assert result[1] is False

    def test_unknown_code(self):
        assert _normalize_error_code("UNKNOWN_CODE") is None


class TestIsTimeoutError:
    def test_timeout_error(self):
        assert _is_timeout_error(TimeoutError()) is True

    def test_socket_timeout(self):
        assert _is_timeout_error(socket.timeout()) is True

    def test_httpx_timeout(self):
        assert _is_timeout_error(httpx.TimeoutException("t")) is True

    def test_not_timeout(self):
        assert _is_timeout_error(ValueError()) is False


class TestIsTransportError:
    def test_connection_error(self):
        assert _is_transport_error(ConnectionError()) is True

    def test_connection_reset(self):
        assert _is_transport_error(ConnectionResetError()) is True

    def test_broken_pipe(self):
        assert _is_transport_error(BrokenPipeError()) is True

    def test_httpx_transport(self):
        assert _is_transport_error(httpx.TransportError("t")) is True

    def test_os_error_with_known_errno(self):
        err = OSError()
        err.errno = 104
        assert _is_transport_error(err) is True

    def test_os_error_with_network_keyword(self):
        err = OSError("connection reset by peer")
        assert _is_transport_error(err) is True

    def test_os_error_unrelated(self):
        err = OSError("file not found")
        err.errno = 2
        assert _is_transport_error(err) is False

    def test_value_error(self):
        assert _is_transport_error(ValueError()) is False


class TestMapHttpStatusToType:
    def test_none(self):
        assert _map_http_status_to_type(None) is None

    def test_400(self):
        assert _map_http_status_to_type(400) == XianGuanJiaErrorType.HTTP_BAD_REQUEST

    def test_401(self):
        assert _map_http_status_to_type(401) == XianGuanJiaErrorType.HTTP_UNAUTHORIZED

    def test_403(self):
        assert _map_http_status_to_type(403) == XianGuanJiaErrorType.HTTP_FORBIDDEN

    def test_404(self):
        assert _map_http_status_to_type(404) == XianGuanJiaErrorType.HTTP_NOT_FOUND

    def test_409(self):
        assert _map_http_status_to_type(409) == XianGuanJiaErrorType.HTTP_CONFLICT

    def test_422(self):
        assert _map_http_status_to_type(422) == XianGuanJiaErrorType.HTTP_UNPROCESSABLE

    def test_429(self):
        assert _map_http_status_to_type(429) == XianGuanJiaErrorType.HTTP_TOO_MANY_REQUESTS

    def test_500(self):
        assert _map_http_status_to_type(500) == XianGuanJiaErrorType.HTTP_SERVER_ERROR

    def test_503(self):
        assert _map_http_status_to_type(503) == XianGuanJiaErrorType.HTTP_SERVER_ERROR

    def test_200(self):
        assert _map_http_status_to_type(200) is None


class TestMapError:
    def test_timeout_exc(self):
        err = map_error(exc=TimeoutError("to"), message="timeout")
        assert isinstance(err, XianGuanJiaRetryableError)
        assert err.error_type == XianGuanJiaErrorType.TIMEOUT

    def test_transport_exc(self):
        err = map_error(exc=ConnectionError("conn"))
        assert isinstance(err, XianGuanJiaRetryableError)
        assert err.error_type == XianGuanJiaErrorType.NETWORK_ERROR

    def test_error_type_string(self):
        err = map_error(error_type="TIMEOUT")
        assert err.error_type == XianGuanJiaErrorType.TIMEOUT

    def test_error_code_retryable(self):
        err = map_error(error_code="E429")
        assert isinstance(err, XianGuanJiaRetryableError)

    def test_error_code_non_retryable(self):
        err = map_error(error_code="E401")
        assert isinstance(err, XianGuanJiaNonRetryableError)

    def test_http_status_only(self):
        err = map_error(http_status=404)
        assert err.error_type == XianGuanJiaErrorType.HTTP_NOT_FOUND

    def test_unknown_fallback(self):
        err = map_error()
        assert err.error_type == XianGuanJiaErrorType.UNKNOWN

    def test_empty_message_fallback(self):
        err = map_error(message="")
        assert "XianGuanJia error" in str(err)

    def test_retryable_http_status(self):
        err = map_error(http_status=502)
        assert isinstance(err, XianGuanJiaRetryableError)


class TestIsRetryableError:
    def test_retryable_error_instance(self):
        err = XianGuanJiaRetryableError("r", error_type=XianGuanJiaErrorType.TIMEOUT)
        assert is_retryable_error(err) is True

    def test_non_retryable_error_instance(self):
        err = XianGuanJiaNonRetryableError("nr", error_type=XianGuanJiaErrorType.AUTH_INVALID)
        assert is_retryable_error(err) is False

    def test_timeout_exception(self):
        assert is_retryable_error(TimeoutError()) is True

    def test_transport_exception(self):
        assert is_retryable_error(ConnectionResetError()) is True

    def test_retryable_error_type_string(self):
        assert is_retryable_error("TIMEOUT") is True

    def test_retryable_http_status(self):
        assert is_retryable_error(None, http_status=503) is True

    def test_not_retryable(self):
        assert is_retryable_error(None) is False


class TestOpenPlatformClient:
    """Tests for open_platform_client.py uncovered lines."""

    def _make_client(self):
        from src.integrations.xianguanjia.open_platform_client import OpenPlatformClient
        return OpenPlatformClient(
            base_url="https://test.api",
            app_key="testkey",
            app_secret="testsecret",
        )

    def _mock_success_post(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0, "data": {"id": "1"}, "request_id": "r1"}
        return mock_resp

    def test_create_product(self):
        client = self._make_client()
        with patch("httpx.post", return_value=self._mock_success_post()):
            result = client.create_product({"name": "test"})
            assert result.ok is True

    def test_batch_create_products(self):
        client = self._make_client()
        with patch("httpx.post", return_value=self._mock_success_post()):
            result = client.batch_create_products({"items": []})
            assert result.ok is True

    def test_publish_product(self):
        client = self._make_client()
        with patch("httpx.post", return_value=self._mock_success_post()):
            result = client.publish_product({"product_id": "1"})
            assert result.ok is True

    def test_unpublish_product(self):
        client = self._make_client()
        with patch("httpx.post", return_value=self._mock_success_post()):
            result = client.unpublish_product({"product_id": "1"})
            assert result.ok is True

    def test_edit_product(self):
        client = self._make_client()
        with patch("httpx.post", return_value=self._mock_success_post()):
            result = client.edit_product({"product_id": "1", "price": 100})
            assert result.ok is True

    def test_edit_stock(self):
        client = self._make_client()
        with patch("httpx.post", return_value=self._mock_success_post()):
            result = client.edit_stock({"product_id": "1", "stock": 10})
            assert result.ok is True

    def test_delete_product(self):
        client = self._make_client()
        with patch("httpx.post", return_value=self._mock_success_post()):
            result = client.delete_product({"product_id": "1"})
            assert result.ok is True

    def test_list_products(self):
        client = self._make_client()
        with patch("httpx.post", return_value=self._mock_success_post()):
            result = client.list_products({"page": 1})
            assert result.ok is True

    def test_get_product_detail(self):
        client = self._make_client()
        with patch("httpx.post", return_value=self._mock_success_post()):
            result = client.get_product_detail({"product_id": "1"})
            assert result.ok is True

    def test_list_categories(self):
        client = self._make_client()
        with patch("httpx.post", return_value=self._mock_success_post()):
            result = client.list_categories()
            assert result.ok is True

    def test_list_product_attrs(self):
        client = self._make_client()
        with patch("httpx.post", return_value=self._mock_success_post()):
            result = client.list_product_attrs({"cat_id": "1"})
            assert result.ok is True

    def test_list_skus(self):
        client = self._make_client()
        with patch("httpx.post", return_value=self._mock_success_post()):
            result = client.list_skus({"product_id": "1"})
            assert result.ok is True

    def test_modify_order_price(self):
        client = self._make_client()
        with patch("httpx.post", return_value=self._mock_success_post()):
            result = client.modify_order_price({"order_no": "o1", "price": 100})
            assert result.ok is True

    def test_delivery_order(self):
        client = self._make_client()
        with patch("httpx.post", return_value=self._mock_success_post()):
            result = client.delivery_order({"order_no": "o1"})
            assert result.ok is True

    def test_list_orders(self):
        client = self._make_client()
        with patch("httpx.post", return_value=self._mock_success_post()):
            result = client.list_orders({"page": 1})
            assert result.ok is True

    def test_get_order_detail(self):
        client = self._make_client()
        with patch("httpx.post", return_value=self._mock_success_post()):
            result = client.get_order_detail({"order_no": "o1"})
            assert result.ok is True

    def test_get_order_kam_list(self):
        client = self._make_client()
        with patch("httpx.post", return_value=self._mock_success_post()):
            result = client.get_order_kam_list({"order_no": "o1"})
            assert result.ok is True

    def test_list_authorized_users(self):
        client = self._make_client()
        with patch("httpx.post", return_value=self._mock_success_post()):
            result = client.list_authorized_users()
            assert result.ok is True

    def test_list_express_companies(self):
        client = self._make_client()
        with patch("httpx.post", return_value=self._mock_success_post()):
            result = client.list_express_companies()
            assert result.ok is True

    def test_post_exception(self):
        client = self._make_client()
        with patch("httpx.post", side_effect=ConnectionError("conn err")):
            result = client._post("/test", {})
            assert result.ok is False
            assert result.retryable is True

    def test_post_business_error(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 1001, "msg": "biz error", "request_id": "r1"}
        with patch("httpx.post", return_value=mock_resp):
            result = client._post("/test", {})
            assert result.ok is False


class TestVirtualSupplyClient:
    """Tests for virtual_supply_client.py uncovered lines 80-82."""

    def test_post_exception(self):
        from src.integrations.xianguanjia.virtual_supply_client import VirtualSupplyClient
        client = VirtualSupplyClient(
            base_url="https://test.api",
            app_id="1",
            app_secret="secret",
            mch_id="m1",
            mch_secret="msecret",
        )
        with patch("httpx.post", side_effect=TimeoutError("timeout")):
            result = client._post("/test", {})
            assert result.ok is False
            assert result.retryable is True


class TestSigning:
    """Tests for signing.py line 29."""

    def test_body_md5_none(self):
        result = _body_md5(None)
        from hashlib import md5
        assert result == md5(b"").hexdigest()

    def test_body_md5_string(self):
        result = _body_md5("hello")
        from hashlib import md5
        assert result == md5(b"hello").hexdigest()
