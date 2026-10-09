import hashlib
import json
from decimal import Decimal

import pytest
import responses
from django.conf import settings
from payments import get_payment_model

from payments_przelewy24.api import Przelewy24API, Transaction
from payments_przelewy24.provider import Przelewy24Provider


@pytest.fixture
def config():
    return settings.TEST_P24_CONFIG


@pytest.fixture(autouse=True)
def http():
    # No test can accidentally send requests to a real payment gateway.
    with responses.RequestsMock() as mock:
        yield mock


@pytest.fixture
def api(config):
    with Przelewy24API(config) as client:
        yield client


@pytest.fixture
def transaction():
    return Transaction(
        amount=12024,
        sessionId="session-123",
        currency="PLN",
        description="Book purchase",
        email="customer@example.com",
        country="PL",
        language="pl",
    )


@pytest.fixture
def provider(config):
    instance = Przelewy24Provider(config)
    yield instance
    instance._api.close()


@pytest.fixture
def payment(db):
    return get_payment_model().objects.create(
        variant="przelewy24",
        description="Book purchase",
        total=Decimal("120.24"),
        tax=Decimal("20.00"),
        currency="PLN",
        delivery=Decimal("10.00"),
        billing_email="customer@example.com",
        billing_country_code="PL",
    )


@pytest.fixture
def sign_notification(config):
    def sign(data):
        # Independent implementation of the wire format, not config.generate_sign().
        fields = (
            "merchantId",
            "posId",
            "sessionId",
            "amount",
            "originAmount",
            "currency",
            "orderId",
            "methodId",
            "statement",
        )
        payload = {key: data[key] for key in fields}
        payload["crc"] = config.crc.get_secret_value()
        digest = hashlib.sha384(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
        return {**data, "sign": digest}

    return sign


@pytest.fixture
def notification(payment, config, sign_notification):
    return sign_notification(
        {
            "merchantId": config.merchant_id,
            "posId": config.pos_id,
            "sessionId": str(payment.pk),
            "amount": 12024,
            "originAmount": 12024,
            "currency": "PLN",
            "orderId": 306026561,
            "methodId": 154,
            "statement": "p24 G02 / Zażółć",
        }
    )


@pytest.fixture
def verify_success(http, config):
    return http.add(
        responses.PUT,
        config.endpoints.transactionVerify,
        json={"data": {"status": "success"}, "responseCode": 0},
    )
