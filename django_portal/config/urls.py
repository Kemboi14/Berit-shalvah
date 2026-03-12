"""
URL configuration for Berit Shalvah Financial Services Portal
"""

# Import webhook views
try:
    from apps.loans.sync.webhook_views import (
        odoo_webhook,
        register_webhook,
        unregister_webhook,
        webhook_status,
    )

    _webhook_views_available = True
except Exception:
    _webhook_views_available = False

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),
    # Portal root
    path("", TemplateView.as_view(template_name="berit/home.html"), name="home"),
    # Authentication URLs (custom only — allauth kept under /auth/ to avoid namespace clash)
    path("accounts/", include("apps.accounts.urls", namespace="accounts")),
    path("auth/", include("allauth.urls")),
    # Application URLs
    path("portal/", include("apps.dashboard.urls")),
    # Use modern_urls exclusively for loans (has app_name='loans' with full feature set)
    path("portal/loans/", include("apps.loans.modern_urls")),
    path("portal/documents/", include("apps.documents.urls")),
    # Health check endpoint
    path(
        "health/",
        TemplateView.as_view(template_name="health.html"),
        name="health_check",
    ),
]

# Webhook endpoints only if sync module loaded successfully
if _webhook_views_available:
    urlpatterns += [
        path("api/webhooks/odoo/", odoo_webhook, name="odoo_webhook"),
        path("api/webhooks/register/", register_webhook, name="register_webhook"),
        path("api/webhooks/unregister/", unregister_webhook, name="unregister_webhook"),
        path("api/webhooks/status/", webhook_status, name="webhook_status"),
    ]

# Serve media and static files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

    # Debug toolbar
    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar

        urlpatterns = [
            path("__debug__/", include(debug_toolbar.urls)),
        ] + urlpatterns

# Custom error pages
handler404 = "config.views.custom_404"
handler500 = "config.views.custom_500"
handler403 = "config.views.custom_403"

# Ensure the accounts namespace isn't declared twice via allauth
# allauth URLs are mapped under /auth/ and do NOT re-declare the accounts namespace
