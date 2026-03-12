# -*- coding: utf-8 -*-
"""
URL patterns for modern loan application views with enhanced Odoo sync
"""

from django.urls import path

from . import modern_wizard_views
from . import views as legacy_views

app_name = "loans"

urlpatterns = [
    # ------------------------------------------------------------------ #
    #  Loan application wizard                                             #
    # ------------------------------------------------------------------ #
    path(
        "apply/",
        modern_wizard_views.ModernLoanWizardView.as_view(),
        name="application_wizard",
    ),
    # Alias so legacy templates using loans:modern_application keep working
    path(
        "apply/new/",
        modern_wizard_views.ModernLoanWizardView.as_view(),
        name="modern_application",
    ),
    path(
        "apply/submit/",
        modern_wizard_views.submit_loan_application,
        name="application_submit",
    ),
    # ------------------------------------------------------------------ #
    #  Application list / detail                                           #
    # ------------------------------------------------------------------ #
    path(
        "applications/",
        modern_wizard_views.ApplicationListView.as_view(),
        name="application_list",
    ),
    # UUID primary key – matches LoanApplication.id = UUIDField
    path(
        "applications/<uuid:pk>/",
        modern_wizard_views.ApplicationDetailView.as_view(),
        name="application_detail",
    ),
    # ------------------------------------------------------------------ #
    #  Success page                                                        #
    # ------------------------------------------------------------------ #
    path(
        "apply/success/",
        modern_wizard_views.ApplicationSuccessView.as_view(),
        name="application_success",
    ),
    # ------------------------------------------------------------------ #
    #  Document management                                                 #
    # ------------------------------------------------------------------ #
    path(
        "applications/<uuid:application_id>/documents/upload/",
        legacy_views.upload_document_view,
        name="upload_document",
    ),
    path(
        "applications/<uuid:application_id>/documents/<int:document_id>/delete/",
        legacy_views.delete_document_view,
        name="delete_document",
    ),
    # ------------------------------------------------------------------ #
    #  Collateral management                                               #
    # ------------------------------------------------------------------ #
    path(
        "applications/<uuid:application_id>/collateral/add/",
        legacy_views.add_collateral_view,
        name="add_collateral",
    ),
    path(
        "applications/<uuid:application_id>/collateral/<int:collateral_id>/delete/",
        legacy_views.delete_collateral_view,
        name="delete_collateral",
    ),
    # ------------------------------------------------------------------ #
    #  Guarantor management                                                #
    # ------------------------------------------------------------------ #
    path(
        "applications/<uuid:application_id>/guarantor/add/",
        legacy_views.add_guarantor_view,
        name="add_guarantor",
    ),
    path(
        "applications/<uuid:application_id>/guarantor/<int:guarantor_id>/delete/",
        legacy_views.delete_guarantor_view,
        name="delete_guarantor",
    ),
    # ------------------------------------------------------------------ #
    #  Repayment schedule & agreement                                      #
    # ------------------------------------------------------------------ #
    path(
        "applications/<uuid:application_id>/repayment-schedule/",
        legacy_views.repayment_schedule_view,
        name="repayment_schedule",
    ),
    path(
        "applications/<uuid:application_id>/agreement/",
        legacy_views.download_agreement_view,
        name="download_agreement",
    ),
    # ------------------------------------------------------------------ #
    #  Loan calculator                                                     #
    # ------------------------------------------------------------------ #
    path(
        "calculator/",
        legacy_views.loan_calculator_view,
        name="calculator",
    ),
    path(
        "calculate/",
        legacy_views.calculate_loan_view,
        name="calculate",
    ),
    # ------------------------------------------------------------------ #
    #  Sync status endpoints                                               #
    # ------------------------------------------------------------------ #
    path(
        "applications/<uuid:application_id>/sync-status/",
        modern_wizard_views.get_loan_sync_status,
        name="application_sync_status",
    ),
    path(
        "dashboard/sync-status/",
        modern_wizard_views.get_dashboard_sync_status,
        name="sync_status",
    ),
]
