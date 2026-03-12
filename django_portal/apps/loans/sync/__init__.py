# -*- coding: utf-8 -*-
"""
Real-time sync module for Django-Odoo integration
"""
# Note: Don't import models at top level to avoid Django app loading issues
# Import them inside functions or use lazy imports when needed

default_app_config = 'apps.loans.sync.apps.SyncConfig'
