from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, SecretStr

PRODUCTION_URL = "https://secure.przelewy24.pl/"
SANDBOX_URL = "https://sandbox.przelewy24.pl/"


@dataclass(frozen=True)
class Endpoints:
    testConnection: str
    transactionRequest: str
    transactionRegister: str
    transactionVerify: str
    transactionGetBySessionId: str


class Przelewy24Config(BaseModel):
    """Validated, immutable settings; secrets are masked in representations."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    pos_id: Annotated[int, Field(gt=0)]
    merchant_id: Annotated[int, Field(gt=0)]
    crc: Annotated[SecretStr, Field(min_length=1)]
    api_key: Annotated[SecretStr, Field(min_length=1)]
    sandbox: bool = True
    timeout: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 10.0

    @property
    def endpoints(self) -> Endpoints:
        base = SANDBOX_URL if self.sandbox else PRODUCTION_URL
        return Endpoints(
            testConnection=f"{base}api/v1/testAccess",
            transactionRequest=f"{base}trnRequest",
            transactionRegister=f"{base}api/v1/transaction/register",
            transactionVerify=f"{base}api/v1/transaction/verify",
            transactionGetBySessionId=f"{base}api/v1/transaction/by/sessionId/",
        )

    def generate_sign(self, **kwargs: object) -> str:
        """Hash ordered JSON without changing spaces within field values."""
        payload = {**kwargs, "crc": self.crc.get_secret_value()}
        encoded = json.dumps(
            payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
        return hashlib.sha384(encoded).hexdigest()

    @classmethod
    def from_env(cls, prefix: str = "PAYMENTS_") -> Przelewy24Config:
        names = {
            "pos_id": "POS_ID",
            "merchant_id": "MERCHANT_ID",
            "crc": "CRC",
            "api_key": "API_KEY",
            "sandbox": "SANDBOX",
            "timeout": "TIMEOUT",
        }
        values = {
            field: os.environ[f"{prefix}P24_{suffix}"]
            for field, suffix in names.items()
            if f"{prefix}P24_{suffix}" in os.environ
        }
        return cls.model_validate(values)
