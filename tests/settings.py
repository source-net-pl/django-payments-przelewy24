"""Isolated test settings: dummy credentials and SQLite unless PostgreSQL is selected."""

import os

from payments_przelewy24.config import Przelewy24Config

SECRET_KEY = "test-only-not-for-deployment"
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "tests.apps.example",
    "payments",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
ROOT_URLCONF = "tests.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "tests.wsgi.application"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
if os.getenv("P24_TEST_POSTGRES") == "1":
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("PGDATABASE", "p24"),
        "USER": os.getenv("PGUSER", "postgres"),
        "PASSWORD": os.getenv("PGPASSWORD", ""),
        "HOST": os.getenv("PGHOST", "127.0.0.1"),
        "PORT": os.getenv("PGPORT", "5432"),
    }
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_TZ = True
STATIC_URL = "/static/"
PAYMENT_HOST = "payments.example.com"
PAYMENT_USES_SSL = True
PAYMENT_MODEL = "example.Payment"
TEST_P24_CONFIG = Przelewy24Config(
    pos_id=123, merchant_id=456, crc="test-crc", api_key="test-api-key", sandbox=True
)
PAYMENT_VARIANTS = {
    "default": ("payments.dummy.DummyProvider", {}),
    "przelewy24": (
        "payments_przelewy24.provider.Przelewy24Provider",
        {"config": TEST_P24_CONFIG},
    ),
}
