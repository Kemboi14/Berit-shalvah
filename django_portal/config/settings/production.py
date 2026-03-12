"""
Production settings for Berit Shalvah Financial Services Portal
"""
from .base import *
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

# Override for production
DEBUG = False

# Security settings
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
X_FRAME_OPTIONS = 'DENY'

# Session and cookie security
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Strict'
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_TRUSTED_ORIGINS = ['https://yourdomain.com']

# Database (use production database from environment)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('PORTAL_DB'),
        'USER': config('POSTGRES_USER'),
        'PASSWORD': config('POSTGRES_PASSWORD'),
        'HOST': config('POSTGRES_HOST'),
        'PORT': config('POSTGRES_PORT', default='5432', cast=int),
        'OPTIONS': {
            'sslmode': 'require',
        },
    }
}

# Email configuration for production
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL')

# Static files storage (use Whitenoise for simplicity)
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files storage (could be S3 in production)
DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
MEDIA_URL = f"https://{config('AWS_S3_CUSTOM_DOMAIN')}/"
AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID', default='')
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY', default='')
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='')
AWS_S3_CUSTOM_DOMAIN = config('AWS_S3_CUSTOM_DOMAIN', default='')
AWS_DEFAULT_ACL = 'public-read'
AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='us-east-1')

# Cache configuration (Redis)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': config('REDIS_URL'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# Celery configuration for production
CELERY_BROKER_URL = config('REDIS_URL')
CELERY_RESULT_BACKEND = config('REDIS_URL')
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_EAGER_PROPAGATES = False

# Logging for production
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/app/logs/django.log',
            'maxBytes': 1024*1024*15,  # 15MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/app/logs/django_error.log',
            'maxBytes': 1024*1024*15,  # 15MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['file', 'error_file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps': {
            'handlers': ['file', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Sentry integration
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=True
    )

# CORS settings for production
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    f"https://{domain}" for domain in ALLOWED_HOSTS
]
CORS_ALLOW_CREDENTIALS = True

# WeasyPrint for production
WEASYPRINT_URL = 'http://weasyprint:8011'

# Odoo settings for production
ODOO_URL = config('ODOO_URL', default='https://odoo.yourdomain.com')
ODOO_DB = config('ODOO_DB')
ODOO_USERNAME = config('ODOO_USERNAME')
ODOO_PASSWORD = config('ODOO_PASSWORD')

# Production-specific portal settings
PORTAL_SETTINGS.update({
    'debug_mode': False,
    'show_development_info': False,
    'analytics_enabled': True,
})

# Rate limiting
RATELIMIT_ENABLE = config('RATELIMIT_ENABLE', default=True, cast=bool)
RATELIMIT_USE_CACHE = 'redis'

# File upload validation
MAX_UPLOAD_SIZE = config('MAX_UPLOAD_SIZE', default=20971520, cast=int)  # 20MB

# Security headers
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# Content Security Policy (optional, for enhanced security)
# CSP_DEFAULT_SRC = "'self'"
# CSP_SCRIPT_SRC = "'self' 'unsafe-inline' https://cdn.tailwindcss.com"
# CSP_STYLE_SRC = "'self' 'unsafe-inline' https://cdn.tailwindcss.com"
# CSP_IMG_SRC = "'self' data: https:"

# Health check endpoints
HEALTH_CHECK_URL = '/health/'
HEALTH_CHECK_TOKEN = config('HEALTH_CHECK_TOKEN', default='')

# Backup configuration
BACKUP_RETENTION_DAYS = config('BACKUP_RETENTION_DAYS', default=30, cast=int)

# Monitoring and metrics
METRICS_ENABLED = config('METRICS_ENABLED', default=True, cast=bool)
