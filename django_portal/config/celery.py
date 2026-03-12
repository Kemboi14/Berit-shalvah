# -*- coding: utf-8 -*-
"""
Celery configuration for Berit Shalvah Financial Services Portal
"""

import os

from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("berit_portal")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related config keys in settings.py
#   must be prefixed with CELERY_ (e.g. CELERY_BROKER_URL).
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps automatically.
# This picks up any tasks.py inside every app listed in INSTALLED_APPS,
# including apps.accounts.tasks, apps.loans.tasks, apps.loans.enhanced_tasks,
# and apps.loans.sync.tasks — so no manual imports are needed here.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task — prints the request repr. Useful for smoke-testing the worker."""
    print(f"Request: {self.request!r}")
