============
Contributing
============

Use an existing checkout and create a branch for your change. From the repository
root, with Python 3.10+::

    python -m venv .venv
    . .venv/bin/activate
    python -m pip install -e '.[dev]'
    python -m pytest --cov=payments_przelewy24
    ruff check .
    ruff format --check .
    mypy

Run ruff format . to format edits. Tests must not use live merchant credentials
or contact Przelewy24. HTTP requests are blocked/mocked automatically by the
shared responses fixture. Add regression tests for changes affecting amounts,
signatures, responses or payment state.

Compatibility matrix
--------------------

Install Python 3.10 through 3.14 and put their executables on PATH, then run::

    tox -p 3

Tox tests Django 5.2 on every supported Python, and Django 6.0/6.1 on Python
3.12 through 3.14. It also checks Django configuration and migration drift.
Missing interpreters are errors, not successful skips. Select one environment
with tox -e py312-django52 or quality checks with tox -e quality.

Dependency ranges are intentional for a reusable library; CI resolves compatible
releases on each run to detect upstream regressions. Do not put an application's
complete lockfile into the library's runtime dependency declarations.

PostgreSQL
----------

The full suite, including simultaneous callbacks using separate DB connections,
runs on PostgreSQL in CI. To reproduce locally, start an isolated test database::

    docker run --rm -d --name p24-test-db \
      -p 127.0.0.1:55432:5432 \
      -e POSTGRES_DB=p24 -e POSTGRES_PASSWORD=test-only postgres:17
    python -m pip install 'psycopg[binary]>=3.2,<4'
    P24_TEST_POSTGRES=1 PGHOST=127.0.0.1 PGPORT=55432 \
      PGDATABASE=p24 PGUSER=postgres PGPASSWORD=test-only \
      python -m pytest --cov=payments_przelewy24
    docker stop p24-test-db

These credentials belong only to the disposable local test database. The Django
test runner creates/drops its test database; its user needs CREATEDB rights.

Packaging
---------

Build and validate both formats::

    python -m build
    python -m twine check --strict dist/*

CI installs the wheel in a fresh virtual environment outside the source tree and
checks that the typed package is present. Distribution artifacts are retained by
GitHub Actions; no package upload or release is triggered.

Before publishing 2.0, complete a sandbox transaction in the consuming staging
application, review MIGRATING.rst, and review the release version/changelog.
