# -*- coding: utf-8 -*-
"""
Django app configuration for sync module
"""
from django.apps import AppConfig


class SyncConfig(AppConfig):
    """Configuration for the sync module"""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.loans.sync'
    verbose_name = 'Odoo Sync'
    
    def ready(self):
        """Import modules when app is ready"""
        # Import signals if needed
        # from . import signals
        pass
