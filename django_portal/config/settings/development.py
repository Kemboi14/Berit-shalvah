"""
Development settings for Berit Shalvah Financial Services Portal
"""
from .base import *

# Override for development
DEBUG = True

# Development database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'berit_portal',
        'USER': 'berit_user',
        'PASSWORD': 'berit123',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# Email backend for development (console)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Debug toolbar (install with: pip install django-debug-toolbar)
if 'debug_toolbar' in INSTALLED_APPS:
    MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
    INTERNAL_IPS = ['127.0.0.1', '0.0.0.0']

# Django extensions
if 'django_extensions' in INSTALLED_APPS:
    SHELL_PLUS_PRINT_SQL = True

# CORS settings for development
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# Static files serving
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# Media files serving
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

# Logging for development
LOGGING['handlers']['file']['level'] = 'DEBUG'
LOGGING['loggers'] = {
    'django': {
        'handlers': ['console', 'file'],
        'level': 'DEBUG',
        'propagate': True,
    },
    'apps': {
        'handlers': ['console', 'file'],
        'level': 'DEBUG',
        'propagate': True,
    },
}

# Celery settings for development
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Cache settings (using dummy cache for development)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# Session settings for development
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Security settings for development
SECURE_SSL_REDIRECT = False
SECURE_BROWSER_XSS_FILTER = False
SECURE_CONTENT_TYPE_NOSNIFF = False

# WeasyPrint for development (disable if not installed)
# WEASYPRINT_URL = None

# Odoo settings for development
ODOO_URL = 'http://localhost:8069'
ODOO_DB = 'berit_odoo'
ODOO_USERNAME = 'admin'
ODOO_PASSWORD = 'admin'

# Development-specific portal settings
PORTAL_SETTINGS.update({
    'debug_mode': True,
    'show_development_info': True,
})

# File upload settings for development (more lenient)
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB for development

# Allow all hosts for development
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']
