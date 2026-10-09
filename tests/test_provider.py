import json
from decimal import Decimal
from unittest.mock import Mock

import pytest
import responses
from django.core.exceptions import ImproperlyConfigured
from payments import PaymentStatus
from payments.signals import status_changed

from payments_przelewy24.forms import ProcessForm
from payments_przelewy24.provider import Przelewy24Provider, _create_transaction_from_payment


def callback(rf, data):
    return rf.post("/callback", data=json.dumps(data), content_type="application/json")


def test_process_form(payment, config, notification):
    form = ProcessForm(payment=payment, config=config, data=notification)
    assert form.is_valid(), form.errors


def test_invalid_form_cannot_save(payment, config):
    form = ProcessForm(payment=payment, config=config, data={})
    with pytest.raises(ValueError):
        form.save()


def test_successful_callback(provider, payment, notification, rf, verify_success, http):
    response = provider.process_data(payment, callback(rf, notification))
    assert response.status_code == 200
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.CONFIRMED
    assert payment.captured_amount == Decimal("120.24")
    assert payment.transaction_id == str(notification["orderId"])
    assert len(http.calls) == 1


def test_duplicate_callback_is_idempotent(
    provider, payment, notification, rf, verify_success, http
):
    received = []

    def receiver(sender, instance, **kwargs):
        received.append(instance.status)

    status_changed.connect(receiver, weak=False)
    try:
        assert provider.process_data(payment, callback(rf, notification)).status_code == 200
        assert provider.process_data(payment, callback(rf, notification)).status_code == 200
    finally:
        status_changed.disconnect(receiver)
    payment.refresh_from_db()
    assert payment.captured_amount == Decimal("120.24")
    assert len(http.calls) == 1
    assert received == [PaymentStatus.CONFIRMED]


def test_callback_after_refund_does_not_recapture(provider, payment, notification, rf, http):
    payment.status = PaymentStatus.REFUNDED
    payment.transaction_id = str(notification["orderId"])
    payment.captured_amount = Decimal("0")
    payment.save()
    assert provider.process_data(payment, callback(rf, notification)).status_code == 200
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.REFUNDED
    assert payment.captured_amount == 0
    assert not http.calls


def test_legacy_confirmed_payment_replay(provider, payment, notification, rf, http):
    payment.status = PaymentStatus.CONFIRMED
    payment.transaction_id = notification["statement"]
    payment.captured_amount = payment.total
    payment.save()
    assert provider.process_data(payment, callback(rf, notification)).status_code == 200
    payment.refresh_from_db()
    assert payment.transaction_id == notification["statement"]
    assert payment.captured_amount == Decimal("120.24")
    assert not http.calls


def test_verify_historical_payment_without_customer_details(
    provider, payment, notification, rf, verify_success
):
    payment.billing_email = ""
    payment.description = ""
    payment.save()
    assert provider.process_data(payment, callback(rf, notification)).status_code == 200
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.CONFIRMED


@pytest.mark.parametrize(
    "field,value",
    [
        ("merchantId", 999),
        ("posId", 999),
        ("sessionId", "other-payment"),
        ("amount", 1),
        ("currency", "EUR"),
    ],
)
def test_even_correctly_signed_mismatch_rejected(
    provider, payment, notification, sign_notification, rf, http, field, value
):
    data = sign_notification({**notification, field: value})
    assert provider.process_data(payment, callback(rf, data)).status_code == 400
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.WAITING
    assert payment.captured_amount == 0
    assert not http.calls


@pytest.mark.parametrize(
    "change",
    [
        {"sign": "0" * 96},
        {"sign": "bad"},
        {"amount": "12024"},
        {"orderId": True},
        {"amount": -1},
        {"methodId": None},
    ],
)
def test_invalid_notification(provider, payment, notification, rf, http, change):
    data = {**notification, **change}
    assert provider.process_data(payment, callback(rf, data)).status_code == 400
    assert not http.calls


@pytest.mark.parametrize("body", [b"{", b"\xff", b"null", b"[]", b"42", b'"text"'])
def test_invalid_json(provider, payment, rf, http, body):
    response = provider.process_data(
        payment, rf.post("/", data=body, content_type="application/json")
    )
    assert response.status_code == 400
    assert not http.calls


def test_get_is_not_a_payment_confirmation(provider, payment, rf, http):
    response = provider.process_data(payment, rf.get("/callback"))
    assert response.status_code == 405
    assert response.headers["Allow"] == "POST"
    assert not http.calls


@pytest.mark.parametrize(
    "status",
    [PaymentStatus.CONFIRMED, PaymentStatus.REJECTED, PaymentStatus.ERROR, PaymentStatus.REFUNDED],
)
def test_conflicting_state(provider, payment, notification, rf, http, status):
    payment.status = status
    payment.transaction_id = "other-order"
    payment.save()
    assert provider.process_data(payment, callback(rf, notification)).status_code == 409
    assert not http.calls


def test_failed_verification_does_not_confirm(provider, payment, notification, config, rf, http):
    http.add(responses.PUT, config.endpoints.transactionVerify, json={"data": {"status": "error"}})
    assert provider.process_data(payment, callback(rf, notification)).status_code == 400
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.WAITING
    assert payment.transaction_id == ""
    assert payment.captured_amount == 0


def test_unavailable_verification_can_be_retried(provider, payment, notification, config, rf, http):
    http.add(responses.PUT, config.endpoints.transactionVerify, status=503, body="private-data")
    http.add(
        responses.PUT, config.endpoints.transactionVerify, json={"data": {"status": "success"}}
    )
    response = provider.process_data(payment, callback(rf, notification))
    assert response.status_code == 503
    assert b"private-data" not in response.content
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.WAITING
    assert payment.captured_amount == 0
    assert provider.process_data(payment, callback(rf, notification)).status_code == 200
    payment.refresh_from_db()
    assert payment.captured_amount == Decimal("120.24")


def test_database_changes_rollback_on_signal_failure(
    provider, payment, notification, rf, verify_success
):
    def receiver(**kwargs):
        raise RuntimeError("receiver failed")

    status_changed.connect(receiver, weak=False)
    try:
        with pytest.raises(RuntimeError, match="receiver failed"):
            provider.process_data(payment, callback(rf, notification))
    finally:
        status_changed.disconnect(receiver)
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.WAITING
    assert payment.captured_amount == 0
    assert payment.transaction_id == ""


def test_missing_field_rejected(provider, payment, notification, rf, http):
    del notification["statement"]
    assert provider.process_data(payment, callback(rf, notification)).status_code == 400
    assert not http.calls


def test_unknown_field_allowed(provider, payment, notification, rf, verify_success):
    notification["futureField"] = "provider-extension"
    assert provider.process_data(payment, callback(rf, notification)).status_code == 200


def test_real_callback_url(client, payment, notification, verify_success):
    response = client.post(payment.get_process_url(), notification, content_type="application/json")
    assert response.status_code == 200
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.CONFIRMED


def test_get_action_uses_payment_urls(provider, payment, config, http):
    http.add(responses.POST, config.endpoints.transactionRegister, json={"data": {"token": "abc"}})
    assert provider.get_action(payment) == "https://sandbox.przelewy24.pl/trnRequest/abc"
    data = json.loads(http.calls[0].request.body)
    assert data["urlStatus"] == "https://payments.example.com" + payment.get_process_url()
    assert data["urlReturn"] == payment.get_success_url()
    assert data["amount"] == 12024
    assert provider.get_hidden_fields(payment) == {}


def test_get_form_integration(provider, payment, config, http):
    http.add(responses.POST, config.endpoints.transactionRegister, json={"data": {"token": "abc"}})
    form = provider.get_form(payment)
    assert form.action == "https://sandbox.przelewy24.pl/trnRequest/abc"
    assert form.method == "get"


def test_preauthorization_rejected(config):
    with pytest.raises(ImproperlyConfigured):
        Przelewy24Provider(config, capture=False)


@pytest.mark.parametrize("total", [Decimal("1.001"), Decimal("NaN"), Decimal("Infinity")])
def test_amount_cannot_be_truncated(total):
    payment = Mock(total=total)
    with pytest.raises(ValueError, match="minor units"):
        _create_transaction_from_payment(payment)
