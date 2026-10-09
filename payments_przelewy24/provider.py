from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.db import router, transaction
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed
from payments import PaymentStatus
from payments.core import BasicProvider
from payments.models import BasePayment

from .api import Przelewy24API
from .config import Przelewy24Config
from .exceptions import Przelewy24Error
from .forms import ProcessForm
from .schemas import Transaction, TransactionReference

logger = logging.getLogger(__name__)


def _create_reference_from_payment(payment: BasePayment) -> TransactionReference:
    amount = Decimal(payment.total) * 100
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise ValueError("Payment total must contain an exact number of minor units")
    return TransactionReference(
        sessionId=str(payment.pk),
        amount=int(amount),
        currency=payment.currency,
    )


def _create_transaction_from_payment(payment: BasePayment) -> Transaction:
    return Transaction(
        **_create_reference_from_payment(payment).model_dump(),
        description=payment.description,
        email=payment.billing_email,
        country=payment.billing_country_code,
        language="pl",
    )


class Przelewy24Provider(BasicProvider):
    """Redirect payments with authenticated, idempotent notifications."""

    _method = "get"

    def __init__(self, config: Przelewy24Config, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if not self._capture:
            raise ImproperlyConfigured("Przelewy24 does not support pre-authorization.")
        self._api = Przelewy24API(config)
        self._config = config

    def get_action(self, payment: BasePayment) -> str:
        return self._api.register(
            transaction=_create_transaction_from_payment(payment),
            success_url=payment.get_success_url(),
            status_url=self.get_return_url(payment),
        )

    def get_hidden_fields(self, payment: BasePayment) -> dict[str, str]:
        return {}

    def process_data(self, payment: BasePayment, request: HttpRequest) -> HttpResponse:
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        try:
            data = json.loads(request.body)
        except (ValueError, UnicodeDecodeError):
            return HttpResponseBadRequest("Invalid JSON")
        if not isinstance(data, dict):
            return HttpResponseBadRequest("Expected a JSON object")

        database = router.db_for_write(type(payment), instance=payment)
        # Serialize callbacks for the same payment, including verification and signals.
        # PostgreSQL is recommended when notifications can arrive concurrently.
        with transaction.atomic(using=database):
            locked = (
                type(payment)
                ._default_manager.using(database)
                .select_for_update()
                .get(pk=payment.pk)
            )
            form = ProcessForm(payment=locked, config=self._config, data=data)
            if not form.is_valid():
                return HttpResponseBadRequest("Invalid notification")
            order_id = form.cleaned_data["orderId"]
            if locked.status in (PaymentStatus.CONFIRMED, PaymentStatus.REFUNDED):
                # Version 0.x stored the statement instead of the numeric order ID.
                if locked.transaction_id in (str(order_id), form.cleaned_data["statement"]):
                    return HttpResponse("OK")
                return HttpResponse("Conflicting transaction", status=409)
            if locked.status not in (PaymentStatus.WAITING, PaymentStatus.INPUT):
                return HttpResponse("Payment cannot be confirmed in its current state", status=409)
            try:
                verified = self._api.verify(
                    transaction=_create_reference_from_payment(locked), orderId=order_id
                )
            except Przelewy24Error:
                logger.warning("Przelewy24 verification unavailable")
                return HttpResponse("Verification unavailable; retry later", status=503)
            if not verified:
                return HttpResponseBadRequest("Verification failed")
            form.save()
            locked.change_status(PaymentStatus.CONFIRMED)
        payment.refresh_from_db(using=database)
        return HttpResponse("OK")
