# -*- coding: utf-8 -*-
from django.apps import AppConfig


class LoansConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.loans'
    verbose_name = 'Loans'
    
    def ready(self):
        """Import signals when app is ready"""
        try:
            import apps.loans.signals
        except ImportError:
            pass
