=======================
Migrating from 0.x to 2.0
=======================

Test this major upgrade in a staging copy of your application using sandbox
credentials before switching a production integration.

Runtime and installation
------------------------

* Upgrade to Python 3.10+ and Django 5.2 LTS, 6.0 or 6.1. Django 6.x requires
  Python 3.12+. Python 3.8 and Django 2.x/3.x are no longer supported.
* Upgrade django-payments to 4.1.x. Review its migration notes, generate migrations
  for your own BasePayment subclass (including inherited fields such as
  billing_phone), and review/apply those migrations.
* Install/build through pip and pyproject.toml. setup.py, Invoke release tasks
  and CircleCI have been replaced by modern build commands and GitHub Actions.
  No publishing job runs automatically.
* The provider itself defines no database models or migrations.

Configuration and Python API
----------------------------

* Przelewy24Config is an immutable Pydantic model. Use keyword arguments or
  from_env(). Positive merchant/POS IDs and nonempty CRC/API keys are required;
  missing variables no longer become dummy credentials.
* Existing PAYMENTS_P24_* variable names and from_env(prefix=...) remain supported.
  Boolean values accept 0/1 and false/true.
* crc and api_key are SecretStr values. Only when explicitly required, access
  contents with .get_secret_value(). str(config.api_key) is masked.
  Configuration and response bodies are no longer logged.
* timeout / PAYMENTS_P24_TIMEOUT defaults to 10 seconds.
* Transaction retains its camelCase wire field names, but is now a Pydantic model
  with keyword-only construction. Use model_dump() instead of dataclasses.asdict().
  Registration requires positive integer minor units, a nonempty description/email,
  and uppercase currency/country.
* TransactionReference in payments_przelewy24.schemas contains just session,
  amount and currency for verification. Historical payments can be verified even
  if customer details are missing.
* test_connection() is preferred; testConnection() remains supported, as do
  verify(transaction=..., orderId=...) and get_by_session_id(session_id=...).
* Internal TransactionDTO, VerifyDTO and _create_sha386_sign() were removed.
* Use Przelewy24Error for API failures. It remains a RuntimeError subclass;
  transport errors no longer escape as raw Requests exceptions.
* get_payment_response() was removed: it referred to undefined members and
  never represented a supported Przelewy24 operation. get_form() and get_action()
  remain the provider integration points.

Payments and callbacks
---------------------

* Merchant ID and POS ID now use their respective configured values.
* Callback URLs remain based on payment.get_process_url(). Registration supplies
  that URL as urlStatus.
* Registration rejects totals requiring truncation of fractional minor units.
  Use exact Decimal values. Historical verification does not require a billing
  email or description.
* Notifications must be JSON objects with integer numeric fields, valid
  signatures and matching payment details. Numeric strings and booleans are
  rejected. Only POST requests are accepted; confirmation requires successful
  server-side verification.
* New confirmations store numeric orderId as a string in payment.transaction_id,
  instead of the bank statement. Adapt code that parses/displays that field.
  Existing confirmed/refunded 0.x rows containing the statement are recognized
  on replay and are not rewritten.
* Captured amount is set to the verified total, never incremented on replay.
  Duplicate callbacks do not send another status_changed signal. Replays after
  full/partial refunds do not restore captured funds.
* Use PostgreSQL or another database with effective row-level locking for
  concurrent webhook delivery. SQLite is intended for local sequential tests.
* Status signals execute inside the transaction. Schedule irreversible external
  effects with transaction.on_commit(). Unexpected errors propagate and roll
  back updates instead of being hidden as HTTP 400.
* Signed JSON preserves spaces, Unicode and slashes inside values. Previous
  signatures incorrectly removed spaces inside values.

Deployment checklist
--------------------

1. Review and apply your application's django-payments model migrations.
2. Check configuration, including distinct merchant/POS IDs where applicable.
3. Exercise registration, customer redirect, asynchronous confirmation and
   repeated notification in Przelewy24 sandbox.
4. Check signal receivers and uses of transaction_id.
5. Switch credentials and sandbox mode through your deployment's secret manager.
   Repository tests do not verify real credentials or provider connectivity.
