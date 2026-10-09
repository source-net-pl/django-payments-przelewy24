import base64
import hashlib
import json
from unittest.mock import Mock

import pytest
import requests
import responses

from payments_przelewy24.api import Przelewy24API
from payments_przelewy24.exceptions import Przelewy24Error


@pytest.mark.parametrize("allowed", [True, False])
def test_connection(api, config, http, allowed):
    http.add(responses.GET, config.endpoints.testConnection, json={"data": allowed})
    assert api.test_connection() is allowed


def test_connection_compatibility_alias(api, config, http):
    http.add(responses.GET, config.endpoints.testConnection, json={"data": True})
    assert api.testConnection() is True


@pytest.mark.parametrize("status", [301, 400, 401, 429, 500])
def test_http_error_never_exposes_response(api, config, http, status):
    http.add(responses.GET, config.endpoints.testConnection, status=status, body="private-data")
    with pytest.raises(Przelewy24Error) as exc:
        api.test_connection()
    assert exc.value.status_code == status
    assert "private-data" not in str(exc.value)
    assert len(http.calls) == 1


@pytest.mark.parametrize("body", ["not json", "[]", "null", "42"])
def test_invalid_json_response(api, config, http, body):
    http.add(responses.GET, config.endpoints.testConnection, body=body)
    with pytest.raises(Przelewy24Error):
        api.test_connection()


@pytest.mark.parametrize("body", [{}, {"data": "true"}, {"data": 1}, {"data": None}])
def test_invalid_access_schema(api, config, http, body):
    http.add(responses.GET, config.endpoints.testConnection, json=body)
    with pytest.raises(Przelewy24Error):
        api.test_connection()


@pytest.mark.parametrize("error", [requests.Timeout, requests.ConnectionError])
def test_transport_failure(api, config, http, error):
    http.add(responses.GET, config.endpoints.testConnection, body=error("sensitive-url"))
    with pytest.raises(Przelewy24Error, match="request failed") as exc:
        api.test_connection()
    assert "sensitive-url" not in str(exc.value)
    assert len(http.calls) == 1


def test_registration_payload(api, transaction, config, http):
    http.add(
        responses.POST, config.endpoints.transactionRegister, json={"data": {"token": "token-123"}}
    )
    url = api.register(
        transaction=transaction,
        success_url="https://shop.example/success",
        status_url="https://shop.example/callback",
    )
    assert url == "https://sandbox.przelewy24.pl/trnRequest/token-123"
    request = http.calls[0].request
    payload = json.loads(request.body)
    assert payload["merchantId"] == 456
    assert payload["posId"] == 123
    assert payload["amount"] == 12024
    assert payload["urlReturn"] == "https://shop.example/success"
    assert payload["urlStatus"] == "https://shop.example/callback"
    wire = (
        b'{"sessionId":"session-123","merchantId":456,"amount":12024,'
        b'"currency":"PLN","crc":"test-crc"}'
    )
    assert payload["sign"] == hashlib.sha384(wire).hexdigest()
    expected_auth = base64.b64encode(b"123:test-api-key").decode()
    assert request.headers["Authorization"] == f"Basic {expected_auth}"


@pytest.mark.parametrize(
    "body", [{}, {"data": {}}, {"data": {"token": ""}}, {"data": {"token": 3}}]
)
def test_invalid_registration_schema(api, transaction, config, http, body):
    http.add(responses.POST, config.endpoints.transactionRegister, json=body)
    with pytest.raises(Przelewy24Error):
        api.register(
            transaction=transaction,
            success_url="https://shop.example/ok",
            status_url="https://shop.example/callback",
        )


@pytest.mark.parametrize("status,expected", [("success", True), ("error", False)])
def test_verification_payload(api, transaction, config, http, status, expected):
    http.add(responses.PUT, config.endpoints.transactionVerify, json={"data": {"status": status}})
    assert api.verify(transaction=transaction, orderId=987) is expected
    payload = json.loads(http.calls[0].request.body)
    assert payload["posId"] == 123
    assert payload["merchantId"] == 456
    assert payload["orderId"] == 987
    wire = (
        b'{"sessionId":"session-123","orderId":987,"amount":12024,'
        b'"currency":"PLN","crc":"test-crc"}'
    )
    assert payload["sign"] == hashlib.sha384(wire).hexdigest()


def test_invalid_verification_response(api, transaction, config, http):
    http.add(responses.PUT, config.endpoints.transactionVerify, json={"data": {}})
    with pytest.raises(Przelewy24Error):
        api.verify(transaction=transaction, orderId=987)


@pytest.mark.parametrize("order", [0, -1, True, 1.5, "123"])
def test_invalid_order_id(api, transaction, order, http):
    with pytest.raises(ValueError):
        api.verify(transaction=transaction, orderId=order)
    assert not http.calls


def test_session_lookup_encodes_path(api, config, http):
    url = config.endpoints.transactionGetBySessionId + "session%2F1%3Fx%3D2"
    http.add(responses.GET, url, json={"data": {"status": 1}})
    assert api.get_by_session_id(session_id="session/1?x=2") == {"data": {"status": 1}}


def test_empty_session_rejected(api):
    with pytest.raises(ValueError):
        api.get_by_session_id(session_id="")


def test_timeout_and_borrowed_session(config):
    session = Mock(spec=requests.Session)
    session.request.return_value.status_code = 200
    session.request.return_value.json.return_value = {"data": True}
    with Przelewy24API(config, session=session) as client:
        assert client.test_connection()
    assert session.request.call_args.kwargs["timeout"] == 10.0
    assert session.request.call_args.kwargs["allow_redirects"] is False
    session.close.assert_not_called()


def test_owned_session_closed(config, monkeypatch):
    session = Mock(spec=requests.Session)
    monkeypatch.setattr(requests, "Session", lambda: session)
    with Przelewy24API(config):
        pass
    session.close.assert_called_once()
