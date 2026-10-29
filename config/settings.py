"""Cấu hình Django cho dự án PawRescue."""

import os
from pathlib import Path
from dotenv import load_dotenv


def env_flag(name, default=False):
    """Đọc biến môi trường dạng đúng/sai theo các giá trị được chấp nhận."""
    fallback = "true" if default else "false"
    return os.getenv(name, fallback).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    """Đọc danh sách từ biến môi trường, tách bằng dấu phẩy và bỏ khoảng trắng thừa."""
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")



SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
DEBUG = env_flag("DJANGO_DEBUG")


ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS",
    "127.0.0.1,localhost" if DEBUG else "",
)
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

if not DEBUG:
    SECURE_SSL_REDIRECT = env_flag("DJANGO_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True



INSTALLED_APPS = [
    'config.admin_site.RescueAdminConfig',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'accounts',
    'organizations.apps.OrganizationsConfig',
    'rescue.apps.RescueConfig',
    'adoptions.apps.AdoptionsConfig',
    'donations.apps.DonationsConfig',
    'support.apps.SupportConfig',
]
AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'rescue.context_processors.unread_notifications',
                'support.context_processors.support_chat',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'



DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}



AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]



LANGUAGE_CODE = 'vi'

TIME_ZONE = 'Asia/Ho_Chi_Minh'

USE_I18N = True

USE_TZ = True




STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'
PRIVATE_SUPPORT_MEDIA_ROOT = BASE_DIR / 'private_media' / 'support'
PRIVATE_DONATION_MEDIA_ROOT = BASE_DIR / 'private_media' / 'donations'
PRIVATE_RESCUE_MEDIA_ROOT = BASE_DIR / 'private_media' / 'rescue'
MAPTILER_API_KEY = os.getenv("MAPTILER_API_KEY", "").strip()

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'rescue:case-list'
LOGOUT_REDIRECT_URL = 'rescue:case-list'


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
