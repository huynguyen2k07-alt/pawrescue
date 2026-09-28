"""Fast, isolated settings for the automated test and local browser smoke suite."""

import os
from pathlib import Path

from .settings import *  # noqa: F403


TEST_DATABASE_PATH = os.getenv("PAWRESCUE_TEST_DB", ":memory:")
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": TEST_DATABASE_PATH,
    }
}

SECRET_KEY = "pawrescue-test-key-not-for-production"
DEBUG = False
ALLOWED_HOSTS = ["testserver", "127.0.0.1", "localhost"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

_TEST_MEDIA_BASE = Path(os.getenv("PAWRESCUE_TEST_MEDIA", "/tmp/pawrescue-test-media"))
MEDIA_ROOT = _TEST_MEDIA_BASE / "public"
PRIVATE_SUPPORT_MEDIA_ROOT = _TEST_MEDIA_BASE / "support"
PRIVATE_DONATION_MEDIA_ROOT = _TEST_MEDIA_BASE / "donations"
PRIVATE_RESCUE_MEDIA_ROOT = _TEST_MEDIA_BASE / "rescue"
