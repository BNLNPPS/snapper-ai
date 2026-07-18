"""Minimal PostgreSQL settings for package-level Snapper tests.

Connection values may be supplied with ``SNAPPER_TEST_DB_*`` environment
variables. Django creates and removes the test database itself.
"""

import os


SECRET_KEY = "snapper-ai-tests"

INSTALLED_APPS = [
    "snapper_ai",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("SNAPPER_TEST_DB_NAME", "postgres"),
        "USER": os.environ.get("SNAPPER_TEST_DB_USER", ""),
        "PASSWORD": os.environ.get("SNAPPER_TEST_DB_PASSWORD", ""),
        "HOST": os.environ.get("SNAPPER_TEST_DB_HOST", ""),
        "PORT": os.environ.get("SNAPPER_TEST_DB_PORT", ""),
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
