from __future__ import annotations

from typing import Any, TypeVar
from urllib.parse import quote

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .config import Przelewy24Config
from .exceptions import Przelewy24Error
from .schemas import Transaction as Transaction
from .schemas import TransactionReference

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


class _Response(BaseModel):
    model_config = ConfigDict(strict=True, hide_input_in_errors=True)


class _AccessResponse(_Response):
    data: bool


class _RegistrationData(_Response):
    token: str = Field(min_length=1)


class _RegistrationResponse(_Response):
    data: _RegistrationData


class _VerificationData(_Response):
    status: str


class _VerificationResponse(_Response):
    data: _VerificationData


class Przelewy24API:
    """Synchronous client. POST/PUT requests are never automatically retried."""

    def __init__(self, config: Przelewy24Config, session: requests.Session | None = None) -> None:
        self._http = session if session is not None else requests.Session()
        self._owns_session = session is None
        self._config = config

    def close(self) -> None:
        if self._owns_session:
            self._http.close()

    def __enter__(self) -> Przelewy24API:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _do(
        self, method: str, endpoint: str, data: dict[str, object] | None = None
    ) -> dict[str, Any]:
        try:
            response = self._http.request(
                method=method,
                url=endpoint,
                json=data,
                auth=(str(self._config.pos_id), self._config.api_key.get_secret_value()),
                timeout=self._config.timeout,
                allow_redirects=False,
            )
        except requests.RequestException:
            raise Przelewy24Error("Przelewy24 request failed") from None
        if response.status_code != 200:
            raise Przelewy24Error(
                f"Przelewy24 returned HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            payload = response.json()
        except ValueError:
            raise Przelewy24Error("Przelewy24 returned invalid JSON") from None
        if not isinstance(payload, dict):
            raise Przelewy24Error("Przelewy24 returned a non-object response")
        return payload

    @staticmethod
    def _parse(model: type[ResponseModel], payload: dict[str, Any]) -> ResponseModel:
        try:
            return model.model_validate(payload)
        except ValidationError:
            raise Przelewy24Error("Przelewy24 returned an invalid response") from None

    def test_connection(self) -> bool:
        payload = self._do("GET", self._config.endpoints.testConnection)
        return self._parse(_AccessResponse, payload).data

    def testConnection(self) -> bool:
        """Compatibility alias for the 0.x client."""
        return self.test_connection()

    def register(self, *, transaction: Transaction, success_url: str, status_url: str) -> str:
        sign = self._config.generate_sign(
            sessionId=transaction.sessionId,
            merchantId=self._config.merchant_id,
            amount=transaction.amount,
            currency=transaction.currency,
        )
        payload = {
            **transaction.model_dump(),
            "merchantId": self._config.merchant_id,
            "posId": self._config.pos_id,
            "urlReturn": success_url,
            "urlStatus": status_url,
            "sign": sign,
        }
        response = self._do("POST", self._config.endpoints.transactionRegister, payload)
        token = self._parse(_RegistrationResponse, response).data.token
        return f"{self._config.endpoints.transactionRequest}/{quote(token, safe='')}"

    def verify(self, *, transaction: TransactionReference, orderId: int) -> bool:
        if isinstance(orderId, bool) or not isinstance(orderId, int) or orderId <= 0:
            raise ValueError("orderId must be a positive integer")
        payload = {
            "merchantId": self._config.merchant_id,
            "posId": self._config.pos_id,
            "sessionId": transaction.sessionId,
            "amount": transaction.amount,
            "currency": transaction.currency,
            "orderId": orderId,
            "sign": self._config.generate_sign(
                sessionId=transaction.sessionId,
                orderId=orderId,
                amount=transaction.amount,
                currency=transaction.currency,
            ),
        }
        response = self._do("PUT", self._config.endpoints.transactionVerify, payload)
        return self._parse(_VerificationResponse, response).data.status == "success"

    def get_by_session_id(self, *, session_id: str) -> dict[str, Any]:
        if not session_id:
            raise ValueError("session_id must not be empty")
        return self._do(
            "GET", self._config.endpoints.transactionGetBySessionId + quote(session_id, safe="")
        )
