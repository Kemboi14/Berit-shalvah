# -*- coding: utf-8 -*-
"""
URL configuration for accounts app
"""

from django.urls import path

from . import auth_views, simple_views, views

app_name = "accounts"

urlpatterns = [
    # Authentication
    path("login/", auth_views.UnifiedLoginView.as_view(), name="login"),
    path("logout/", auth_views.CustomLogoutView.as_view(), name="logout"),
    path("signup/", auth_views.SignupView.as_view(), name="signup"),
    # AJAX Authentication
    path("ajax-login/", auth_views.ajax_login, name="ajax_login"),
    path("check-user/", auth_views.check_user_exists, name="check_user"),
    # Profile and Settings
    path("profile/", views.profile_view, name="profile"),
    path("profile/edit/", views.ProfileUpdateView.as_view(), name="profile_edit"),
    path("settings/", views.settings_view, name="settings"),
    path("change-password/", views.change_password_view, name="change_password"),
    path("export-data/", views.export_data_view, name="export_data"),
    path(
        "deactivate-account/", views.deactivate_account_view, name="deactivate_account"
    ),
    path("delete-account/", views.delete_account_view, name="delete_account"),
    # Documents
    path("documents/", views.documents_view, name="documents"),
    path("documents/upload/", views.upload_document_view, name="upload_document"),
    path(
        "documents/<int:document_id>/delete/",
        views.delete_document_view,
        name="delete_document",
    ),
    # Verification
    path("verification/", views.verification_requests_view, name="verification"),
    path(
        "verification/submit/",
        views.submit_verification_request,
        name="submit_verification_request",
    ),
    # Dashboard
    path("dashboard/", views.dashboard_view, name="dashboard"),
    # AJAX endpoints
    path("check-email/", views.check_email_view, name="check_email"),
    path("check-national-id/", views.check_national_id_view, name="check_national_id"),
]
