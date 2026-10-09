"""Wire models retain Przelewy24's field names for API compatibility."""

from __future__ import annotations

import hmac
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from .config import Przelewy24Config

PositiveInt = Annotated[int, Field(strict=True, gt=0)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class TransactionReference(BaseModel):
    """Fields needed to verify a previously registered payment."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    amount: PositiveInt
    sessionId: Annotated[str, Field(min_length=1, max_length=100)]
    currency: Currency


class Transaction(TransactionReference):
    description: Annotated[str, Field(min_length=1, max_length=1024)]
    email: Annotated[str, Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+$")]
    country: Annotated[str, Field(pattern=r"^[A-Z]{2}$")] = "PL"
    language: Annotated[str, Field(pattern=r"^[a-z]{2}$")] = "pl"


class Notification(BaseModel):
    # Ignore future provider additions, but never coerce signed fields.
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)

    merchantId: PositiveInt
    posId: PositiveInt
    sessionId: str
    amount: PositiveInt
    originAmount: PositiveInt
    currency: Currency
    orderId: PositiveInt
    methodId: PositiveInt
    statement: Annotated[str, Field(min_length=1)]
    sign: Annotated[str, Field(pattern=r"^[a-fA-F0-9]{96}$")]

    def validate_payment(
        self, *, config: Przelewy24Config, session_id: str, total: Decimal, currency: str
    ) -> None:
        expected = config.generate_sign(**self.model_dump(exclude={"sign"}))
        if not hmac.compare_digest(self.sign.lower(), expected):
            raise ValueError("Invalid notification signature")
        if self.merchantId != config.merchant_id or self.posId != config.pos_id:
            raise ValueError("Notification merchant or POS does not match")
        if self.sessionId != session_id:
            raise ValueError("Notification session does not match")
        if self.currency != currency or Decimal(self.amount) / 100 != total:
            raise ValueError("Notification amount or currency does not match")
