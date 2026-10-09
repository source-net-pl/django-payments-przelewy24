=============================
django-payments-przelewy24
=============================

Przelewy24 REST API integration for django-payments_. Version 2.0 adds typed,
validated configuration and payloads, bounded HTTP requests, and idempotent
payment notifications. This branch prepares the 2.0 release.

Supported versions
------------------

=================  ====================
Python             Django
=================  ====================
3.10, 3.11         5.2 LTS
3.12, 3.13, 3.14   5.2 LTS, 6.0, 6.1
=================  ====================

Requires django-payments 4.1.x, Pydantic 2.12+ within 2.x, and Requests 2.x.
CI tests all 11 Python/Django combinations, PostgreSQL callback concurrency,
strict types, linting and distribution builds. SQLite works for local tests;
use a database supporting row locks, such as PostgreSQL, for concurrent
payment notifications.

Installation and configuration
------------------------------

Until 2.0 is published, install this checkout with::

    python -m pip install .

After publication::

    python -m pip install 'django-payments-przelewy24>=2,<3'

Configure django-payments with your application's BasePayment subclass,
PAYMENT_MODEL, PAYMENT_HOST and PAYMENT_USES_SSL = True. Include payments.urls
in your URL configuration. Configure the provider in Django settings:

.. code-block:: python

    from payments_przelewy24.config import Przelewy24Config

    PAYMENT_VARIANTS = {
        "przelewy24": (
            "payments_przelewy24.provider.Przelewy24Provider",
            {"config": Przelewy24Config.from_env()},
        ),
    }

Provide these variables through your application's secret manager or environment:

* **PAYMENTS_P24_POS_ID**: positive POS identifier.
* **PAYMENTS_P24_MERCHANT_ID**: positive merchant identifier; it can differ from POS.
* **PAYMENTS_P24_CRC**: merchant CRC key.
* **PAYMENTS_P24_API_KEY**: REST API key.
* **PAYMENTS_P24_SANDBOX**: 1 / true for sandbox (default), 0 / false for production.
* **PAYMENTS_P24_TIMEOUT**: positive timeout in seconds (default: 10).

Missing credentials or invalid configuration raise pydantic.ValidationError at
startup. Explicit keyword construction of Przelewy24Config is also supported.
Secrets use SecretStr and are masked in representations and JSON.

Create payments with variant="przelewy24", a positive total with at most two
decimal places, a three-letter uppercase currency, a nonempty description and
billing email, and a two-letter uppercase billing country. Construct totals from
strings, for example Decimal("120.24").

payment.get_form() registers the transaction and returns a GET form that sends
the customer to Przelewy24. Its success URL comes from get_success_url(); the
asynchronous status URL is django-payments' per-payment callback URL. Expose
that callback over HTTPS so Przelewy24 can deliver JSON notifications.
The customer's return to your site does not confirm payment.

Notifications
-------------

Confirmation requires a valid SHA-384 signature, matching merchant, POS, session,
amount and currency, and successful verification with Przelewy24. The handler
locks the payment row while verifying and updating it:

* Valid notifications return HTTP 200 and capture the payment once.
* Repeated notifications for the same confirmed or refunded transaction return
  HTTP 200 without changing captured funds or emitting another status signal.
* Invalid payloads or negative verification return HTTP 400; incompatible payment
  state or a conflicting transaction returns HTTP 409.
* API, transport or response-format failures return HTTP 503 so delivery can be
  retried. Non-POST requests return HTTP 405.
* Unexpected application/database errors propagate to Django. Database updates
  roll back; external work in signal receivers should use transaction.on_commit.

The client does not automatically retry registration or verification. Each
Requests timeout bounds socket connection/read inactivity, not total wall time.
Pre-authorization, refunds initiated through this provider, recurring payments,
and automatic currency conversion are not implemented.

Standalone API
--------------

.. code-block:: python

    from payments_przelewy24.api import Przelewy24API, Transaction
    from payments_przelewy24.config import Przelewy24Config
    from payments_przelewy24.exceptions import Przelewy24Error

    config = Przelewy24Config.from_env()
    with Przelewy24API(config) as api:
        available = api.test_connection()
        transaction = Transaction(
            amount=12024,
            sessionId="order-123",
            currency="PLN",
            description="Book purchase",
            email="customer@example.com",
            country="PL",
            language="pl",
        )
        redirect_url = api.register(
            transaction=transaction,
            success_url="https://shop.example/success",
            status_url="https://shop.example/payment-status",
        )

The API raises Przelewy24Error (a RuntimeError subclass) for transport, HTTP and
response-validation errors. HTTP failures expose status_code without including
response bodies. Input errors use Pydantic's ValidationError or ValueError.
An injected requests.Session remains owned by the caller. testConnection()
remains an alias for test_connection().

Development
-----------

From the repository root::

    python -m venv .venv
    . .venv/bin/activate
    python -m pip install -e '.[dev]'
    python -m pytest --cov=payments_przelewy24
    ruff check .
    ruff format --check .
    mypy
    tox -p 3

Tox requires the selected Python interpreters on PATH and fails when one is
missing. Run a single combination with tox -e py312-django52. All automated HTTP
calls are mocked and use fixed test credentials; tests never register a real
payment. The PostgreSQL-only concurrency test is skipped on SQLite and runs in
its own CI job. Coverage includes branches with a minimum threshold of 90%.

See CONTRIBUTING.rst_ for PostgreSQL and build checks and MIGRATING.rst_ before
upgrading from 0.x. Verify an actual sandbox checkout and payment notification
in your staging application before deploying 2.0.

.. _django-payments: https://django-payments.readthedocs.io/
.. _CONTRIBUTING.rst: CONTRIBUTING.rst
.. _MIGRATING.rst: MIGRATING.rst
