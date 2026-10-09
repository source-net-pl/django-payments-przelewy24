import hashlib
import json

import pytest
from pydantic import ValidationError

from payments_przelewy24.config import Przelewy24Config
from payments_przelewy24.schemas import Transaction


def test_secrets_are_masked(config, caplog):
    with caplog.at_level("DEBUG"):
        another = Przelewy24Config.model_validate(config.model_dump())
    for output in (repr(another), str(another), another.model_dump_json(), caplog.text):
        assert "test-api-key" not in output
        assert "test-crc" not in output


def test_signature_preserves_spaces_unicode_and_slashes(config):
    wire = '{"sessionId":"a b/ż","amount":100,"crc":"test-crc"}'.encode()
    assert config.generate_sign(sessionId="a b/ż", amount=100) == hashlib.sha384(wire).hexdigest()
    assert config.generate_sign(sessionId="a b") != config.generate_sign(sessionId="ab")


def test_signature_field_order_matters(config):
    assert config.generate_sign(a=1, b=2) != config.generate_sign(b=2, a=1)


def test_configuration_is_immutable(config):
    with pytest.raises(ValidationError):
        config.pos_id = 22


@pytest.mark.parametrize(
    "field,value",
    [
        ("pos_id", 0),
        ("merchant_id", -1),
        ("crc", ""),
        ("api_key", ""),
        ("timeout", 0),
        ("timeout", -1),
        ("timeout", float("inf")),
        ("timeout", float("nan")),
        ("sandbox", "maybe"),
        ("typo", True),
    ],
)
def test_invalid_config(config, field, value):
    with pytest.raises(ValidationError):
        Przelewy24Config.model_validate({**config.model_dump(), field: value})


@pytest.mark.parametrize("sandbox", [True, False])
def test_endpoints(config, sandbox):
    configured = Przelewy24Config.model_validate({**config.model_dump(), "sandbox": sandbox})
    host = "sandbox" if sandbox else "secure"
    assert configured.endpoints.transactionGetBySessionId == (
        f"https://{host}.przelewy24.pl/api/v1/transaction/by/sessionId/"
    )


@pytest.mark.parametrize(
    "flag,expected", [("1", True), ("0", False), ("true", True), ("false", False)]
)
def test_from_env(monkeypatch, flag, expected):
    values = {
        "POS_ID": "123",
        "MERCHANT_ID": "456",
        "CRC": "test-crc",
        "API_KEY": "test-key",
        "SANDBOX": flag,
        "TIMEOUT": "2.5",
    }
    for name, value in values.items():
        monkeypatch.setenv(f"CUSTOM_P24_{name}", value)
    configured = Przelewy24Config.from_env(prefix="CUSTOM_")
    assert configured.pos_id == 123
    assert configured.merchant_id == 456
    assert configured.sandbox is expected
    assert configured.timeout == 2.5
    assert configured.api_key.get_secret_value() == "test-key"


def test_missing_environment_fails_without_placeholder_credentials():
    with pytest.raises(ValidationError) as exc:
        Przelewy24Config.from_env(prefix="UNCONFIGURED_TEST_")
    assert {e["loc"][0] for e in exc.value.errors()} == {"pos_id", "merchant_id", "api_key", "crc"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("amount", 0),
        ("amount", -1),
        ("amount", True),
        ("amount", 1.2),
        ("amount", "100"),
        ("currency", "pln"),
        ("currency", "PLNN"),
        ("sessionId", ""),
        ("description", ""),
        ("email", "not-an-email"),
        ("country", "pol"),
        ("language", "PL"),
    ],
)
def test_transaction_validation(transaction, field, value):
    with pytest.raises(ValidationError):
        Transaction.model_validate({**transaction.model_dump(), field: value})


def test_transaction_serialization(transaction):
    assert json.loads(transaction.model_dump_json())["amount"] == 12024
