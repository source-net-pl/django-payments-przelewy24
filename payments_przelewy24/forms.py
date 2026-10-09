from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms
from payments.models import BasePayment
from pydantic import ValidationError

from .config import Przelewy24Config
from .schemas import Notification


class ProcessForm(forms.Form):
    """Compatibility adapter; validation alone never confirms a payment."""

    merchantId = forms.IntegerField()
    posId = forms.IntegerField()
    sessionId = forms.CharField()
    amount = forms.IntegerField()
    originAmount = forms.IntegerField()
    currency = forms.CharField()
    orderId = forms.IntegerField()
    methodId = forms.IntegerField()
    statement = forms.CharField(strip=False)
    sign = forms.CharField()

    def __init__(self, payment: BasePayment, config: Przelewy24Config, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.config = config
        self.payment = payment

    def clean(self) -> dict[str, Any]:
        super().clean()
        try:
            notification = Notification.model_validate(self.data)
            notification.validate_payment(
                config=self.config,
                session_id=str(self.payment.pk),
                total=Decimal(self.payment.total),
                currency=self.payment.currency,
            )
        except (ValidationError, ValueError):
            raise forms.ValidationError("Invalid Przelewy24 notification") from None
        return notification.model_dump()

    def save(self) -> None:
        """Persist verified data; call only after the API verification succeeds."""
        if not self.is_valid():
            raise ValueError("Cannot save an invalid notification")
        self.payment.transaction_id = str(self.cleaned_data["orderId"])
        self.payment.captured_amount = Decimal(self.cleaned_data["amount"]) / 100
        # django-payments overrides Model.save() without a typed signature.
        self.payment.save(  # type: ignore[no-untyped-call]
            update_fields=["transaction_id", "captured_amount"]
        )
