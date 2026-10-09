# Test application

This Django project exercises the provider and its per-payment callback URL.
Run tests from the repository root:

~~~sh
python -m pip install -e '.[test]'
python -m pytest --cov=payments_przelewy24
~~~

Settings use dummy Przelewy24 credentials and an in-memory SQLite database.
HTTP is mocked by the suite. No external credentials are required.
Example model migrations track current django-payments inherited fields.

For PostgreSQL concurrency tests, follow CONTRIBUTING.rst and set
P24_TEST_POSTGRES=1. This test app is not a deployable shop or a live payment demo.
