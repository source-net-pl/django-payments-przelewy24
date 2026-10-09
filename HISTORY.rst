.. :changelog:

History
-------

2.0.0 (unreleased)
++++++++++++++++++

* Support Python 3.10–3.14, Django 5.2/6.0/6.1 and django-payments 4.1.
* Replace legacy packaging with pyproject.toml, typed distributions and modern
  development tooling (Ruff, strict mypy and tox).
* Validate configuration, transactions, notifications and API responses with
  Pydantic 2; mask secrets and remove sensitive request/response logging.
* Add HTTP timeouts, safe errors, explicit session ownership and encoded lookup
  paths; correct the POS identifier and signed JSON serialization.
* Reject invalid/mismatched notifications and negative API verification; capture
  atomically and idempotently, including concurrent PostgreSQL deliveries.
* Retain compatibility aliases and recognize notifications for legacy confirmed
  payments. Document breaking changes in MIGRATING.rst.
* Replace CircleCI with an 11-combination GitHub Actions matrix, PostgreSQL
  concurrency tests, quality checks and distribution smoke tests.

0.1.0 (2021-01-27)
++++++++++++++++++

* First release on PyPI.
