"""
Base settings for Berit Shalvah Financial Services Portal
"""

import os
from pathlib import Path

from decouple import config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config("SECRET_KEY", default="django-insecure-change-me-in-production")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config("DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1",
    cast=lambda v: [s.strip() for s in v.split(",")],
)

# Application definition
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
]

THIRD_PARTY_APPS = [
    "django.contrib.admindocs",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "crispy_forms",
    "crispy_tailwind",
    "widget_tweaks",
    "corsheaders",
    "storages",
    "django_extensions",
    "django_celery_beat",
    "django_celery_results",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.loans",
    "apps.documents",
    "apps.dashboard",
    "apps.loans.sync.apps.SyncConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "config.context_processors.portal_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("PORTAL_DB", default="berit_portal"),
        "USER": config("POSTGRES_USER", default="berit_user"),
        "PASSWORD": config("POSTGRES_PASSWORD", default="password"),
        "HOST": config("POSTGRES_HOST", default="localhost"),
        "PORT": config("POSTGRES_PORT", default="5432", cast=int),
    }
}

# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom User Model
AUTH_USER_MODEL = "accounts.User"

# Django Allauth Configuration
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

SITE_ID = 1

# New django-allauth 0.57+ settings API (deprecated settings removed)
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_RATE_LIMITS = {
    "login_failed": "5/5m",  # 5 failed attempts per 5 minutes
}

# Email Configuration
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL", default="Berit Shalvah <noreply@beritshalvah.co.ke>"
)

# Celery Configuration
CELERY_BROKER_URL = config("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = config("REDIS_URL", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# Celery Beat Schedule for Automatic Odoo Synchronization
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # Sync loan statuses from Odoo every 15 minutes
    "sync-loan-statuses-from-odoo": {
        "task": "apps.loans.enhanced_tasks.periodic_status_sync",
        "schedule": crontab(minute="*/15"),
    },
    # Complete sync every 30 minutes
    "complete-loan-sync": {
        "task": "apps.loans.enhanced_tasks.periodic_sync_all",
        "schedule": crontab(minute="*/30"),
    },
    # Sync repayment schedules every hour
    "sync-repayment-schedules": {
        "task": "apps.loans.enhanced_tasks.periodic_repayment_sync",
        "schedule": crontab(minute=0, hour="*/1"),
    },
    # Auto-sync new applications every 5 minutes
    "auto-sync-new-applications": {
        "task": "apps.loans.enhanced_tasks.auto_sync_new_applications",
        "schedule": crontab(minute="*/5"),
    },
    # Clean up expired sessions every 6 hours
    "cleanup-expired-sessions": {
        "task": "apps.accounts.tasks.cleanup_expired_sessions",
        "schedule": crontab(minute=0, hour="*/6"),
    },
    # Deactivate accounts unverified for more than 30 days — runs daily at 02:00
    "deactivate-unverified-accounts": {
        "task": "apps.accounts.tasks.deactivate_unverified_accounts",
        "schedule": crontab(minute=0, hour=2),
    },
}

# Crispy Forms
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# Tailwind CSS (using crispy-tailwind)
CRISPY_TAILWIND = True

# File Upload Settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024  # 20MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024  # 20MB
MAX_UPLOAD_SIZE = config("MAX_UPLOAD_SIZE", default=20971520, cast=int)

# Allowed file types for document uploads
ALLOWED_DOCUMENT_TYPES = config(
    "ALLOWED_DOCUMENT_TYPES",
    default="pdf,jpg,jpeg,png,doc,docx",
    cast=lambda v: [s.strip().lower() for s in v.split(",")],
)

# Security Settings
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False, cast=bool
)
SECURE_HSTS_PRELOAD = config("SECURE_HSTS_PRELOAD", default=False, cast=bool)

# CORS Settings
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

# Logging Configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "logs" / "django.log",
            "formatter": "verbose",
        },
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
}

# Portal Settings (for context processor)
PORTAL_SETTINGS = {
    "company_name": config(
        "COMPANY_NAME", default="Berit Shalvah Financial Services Ltd"
    ),
    "company_address": config("COMPANY_ADDRESS", default="Kiambu County, Kenya"),
    "company_phone": config("COMPANY_PHONE", default="+254-XXX-XXX-XXX"),
    "company_email": config("COMPANY_EMAIL", default="beritfinance@gmail.com"),
    "portal_base_url": config("PORTAL_BASE_URL", default="http://localhost:8000"),
}

# Loan Interest Rates (matching Odoo configuration)
INTEREST_RATES = [
    {"min_amount": 1, "max_amount": 99999, "rate": 20.0},
    {"min_amount": 100000, "max_amount": 399999, "rate": 17.5},
    {"min_amount": 400000, "max_amount": 599999, "rate": 15.0},
    {"min_amount": 600000, "max_amount": 799999, "rate": 10.0},
    {"min_amount": 800000, "max_amount": 999999, "rate": 7.5},
    {"min_amount": 1000000, "max_amount": 0, "rate": 5.0},  # 0 means no upper limit
]

# Loan Configuration
LOAN_CONFIG = {
    "min_amount": 1000,
    "max_amount": 5000000,
    "min_duration_months": 1,
    "max_duration_months_new": 3,  # For first-time applicants
    "max_duration_months_returning": 12,  # For returning applicants
    "legal_fee_percentage": 2.5,  # 2.5% of loan amount
    "collateral_multiplier": 1.5,  # 1.5x loan amount
}

# WeasyPrint Configuration
WEASYPRINT_URL = "http://localhost:8001"

# Odoo Integration Settings
ODOO_URL = config("ODOO_URL", default="http://localhost:8069")
ODOO_DB = config("ODOO_DB", default="berit_odoo")
ODOO_USERNAME = config("ODOO_USERNAME", default="admin")
ODOO_PASSWORD = config("ODOO_PASSWORD", default="admin")

# Webhook Settings for Real-time Sync
ODOO_WEBHOOK_URL = config(
    "ODOO_WEBHOOK_URL", default="http://localhost:8000/api/webhooks/odoo/"
)
ODOO_WEBHOOK_SECRET = config("ODOO_WEBHOOK_SECRET", default="")
SYNC_MAX_RETRIES = 3
SYNC_RETRY_DELAY = 60
SYNC_LOCK_TTL = 300

# Session Settings
SESSION_COOKIE_AGE = 86400 * 7  # 7 days
SESSION_SAVE_EVERY_REQUEST = True

# Message Framework
from django.contrib.messages import constants as messages

MESSAGE_TAGS = {
    messages.DEBUG: "debug",
    messages.INFO: "info",
    messages.SUCCESS: "success",
    messages.WARNING: "warning",
    messages.ERROR: "error",
}
