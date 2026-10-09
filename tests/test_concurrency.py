import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import Mock

import pytest
from django.db import close_old_connections, connection
from django.test import RequestFactory
from payments import PaymentStatus


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_simultaneous_notifications_capture_only_once(provider, payment, notification):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL SELECT FOR UPDATE semantics")

    ready = Barrier(2)
    provider._api.verify = Mock(return_value=True)

    def deliver():
        close_old_connections()
        try:
            stale_payment = type(payment).objects.get(pk=payment.pk)
            request = RequestFactory().post(
                "/callback", data=json.dumps(notification), content_type="application/json"
            )
            ready.wait(timeout=10)
            return provider.process_data(stale_payment, request).status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(deliver) for _ in range(2)]
        assert [future.result(timeout=20) for future in futures] == [200, 200]

    payment.refresh_from_db()
    assert payment.status == PaymentStatus.CONFIRMED
    assert payment.captured_amount == Decimal("120.24")
    provider._api.verify.assert_called_once()
