"""
Custom views for error pages and other utilities
"""
from django.shortcuts import render
from django.http import HttpResponseNotFound, HttpResponseServerError, HttpResponseForbidden


def custom_404(request, exception):
    """Custom 404 error page"""
    return render(request, 'berit/errors/404.html', status=404)


def custom_500(request):
    """Custom 500 error page"""
    return render(request, 'berit/errors/500.html', status=500)


def custom_403(request, exception):
    """Custom 403 error page"""
    return render(request, 'berit/errors/403.html', status=403)
