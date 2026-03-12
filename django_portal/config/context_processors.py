"""
Context processors for Berit Shalvah Financial Services Portal
"""
from django.conf import settings


def portal_settings(request):
    """
    Global context processor for portal settings
    """
    return {
        'portal_settings': getattr(settings, 'PORTAL_SETTINGS', {}),
        'interest_rates': getattr(settings, 'INTEREST_RATES', []),
        'loan_config': getattr(settings, 'LOAN_CONFIG', {}),
    }
