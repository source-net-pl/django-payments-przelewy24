import uuid
from collections.abc import Iterable
from decimal import Decimal

from django.db import models
from payments import PurchasedItem
from payments.models import BasePayment


class Payment(BasePayment):
    id = models.CharField(primary_key=True, editable=False, default=uuid.uuid4, max_length=50)

    def get_failure_url(self) -> str:
        return "https://przelewy24.source.net.pl/fail"

    def get_success_url(self) -> str:
        return "https://przelewy24.source.net.pl/success"

    def get_purchased_items(self) -> Iterable[PurchasedItem]:
        # you'll probably want to retrieve these from an associated order
        yield PurchasedItem(
            name="The Hound of the Baskervilles",
            sku="BSKV",
            quantity=9,
            price=Decimal(10),
            currency="USD",
        )
