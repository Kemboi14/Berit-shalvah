# -*- coding: utf-8 -*-
"""
Views for loan application management
"""

import json
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.storage import default_storage
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import (
    LoanApplicationForm,
    LoanCollateralForm,
    LoanDocumentForm,
    LoanGuarantorForm,
)
from .models import (
    LoanApplication,
    LoanCollateral,
    LoanDocument,
    LoanGuarantor,
    RepaymentSchedule,
)
from .utils import LoanCalculator, OdooIntegration


@login_required
def loan_application_wizard(request):
    """Multi-step loan application wizard"""

    # Get or create draft application
    application = LoanApplication.objects.filter(
        user=request.user, status=LoanApplication.Status.DRAFT
    ).first()

    if not application:
        application = LoanApplication.objects.create(
            user=request.user, status=LoanApplication.Status.DRAFT
        )

    if request.method == "POST":
        step = request.POST.get("step", "1")

        if step == "1":
            # Loan details step
            form = LoanApplicationForm(request.POST, instance=application)
            if form.is_valid():
                form.save()
                return JsonResponse({"success": True, "next_step": "2"})
            else:
                return JsonResponse({"success": False, "errors": form.errors})

        elif step == "2":
            # KYC documents step
            # Handle document uploads
            documents_data = json.loads(request.POST.get("documents", "[]"))

            for doc_data in documents_data:
                doc_form = LoanDocumentForm(doc_data)
                if doc_form.is_valid():
                    document = doc_form.save(commit=False)
                    document.loan_application = application
                    document.save()

            return JsonResponse({"success": True, "next_step": "3"})

        elif step == "3":
            # Collateral step
            collateral_data = json.loads(request.POST.get("collateral", "{}"))

            if collateral_data:
                collateral_form = LoanCollateralForm(collateral_data, request.FILES)
                if collateral_form.is_valid():
                    collateral = collateral_form.save(commit=False)
                    collateral.loan_application = application
                    collateral.save()

            return JsonResponse({"success": True, "next_step": "4"})

        elif step == "4":
            # Guarantor step
            guarantor_data = json.loads(request.POST.get("guarantor", "{}"))

            if guarantor_data:
                guarantor_form = LoanGuarantorForm(guarantor_data, request.FILES)
                if guarantor_form.is_valid():
                    guarantor = guarantor_form.save(commit=False)
                    guarantor.loan_application = application
                    guarantor.save()

            return JsonResponse({"success": True, "next_step": "5"})

        elif step == "5":
            # Review and submit step
            application.status = LoanApplication.Status.SUBMITTED
            application.submitted_at = timezone.now()
            application.save()

            # Send to Odoo
            try:
                odoo_integration = OdooIntegration()
                odoo_id = odoo_integration.create_loan_application(application)
                application.odoo_application_id = odoo_id
                application.save()

                # Send notification email
                # TODO: Implement email notification

                messages.success(
                    request,
                    f"Loan application submitted successfully! Reference: {application.reference_number}",
                )
                return JsonResponse(
                    {
                        "success": True,
                        "redirect": reverse_lazy(
                            "loans:application_detail", args=[application.id]
                        ),
                    }
                )

            except Exception as e:
                messages.error(request, f"Error submitting application: {str(e)}")
                return JsonResponse({"success": False, "error": str(e)})

    # GET request - show current step
    context = {
        "application": application,
        "completion_percentage": application.get_completion_percentage(),
        "loan_config": getattr(settings, "LOAN_CONFIG", {}),
    }

    return render(request, "berit/loans/application_wizard.html", context)


class LoanApplicationDetailView(LoginRequiredMixin, DetailView):
    """View loan application details"""

    model = LoanApplication
    template_name = "berit/loans/application_detail.html"
    context_object_name = "application"

    def get_queryset(self):
        return LoanApplication.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        application = self.get_object()

        # Get related objects
        context["documents"] = application.documents.all()
        context["collaterals"] = application.collaterals.all()
        context["guarantors"] = application.guarantors.all()
        context["repayment_schedule"] = application.repayment_schedule.all().order_by(
            "installment_number"
        )

        # Calculate totals
        if application.repayment_schedule.exists():
            total_paid = sum(
                r.amount_paid for r in application.repayment_schedule.all()
            )
            total_due = sum(r.total_due for r in application.repayment_schedule.all())
            context["total_paid"] = total_paid
            context["total_due"] = total_due
            context["outstanding_balance"] = total_due - total_paid

        return context


class LoanApplicationListView(LoginRequiredMixin, ListView):
    """List user's loan applications"""

    model = LoanApplication
    template_name = "berit/loans/application_list.html"
    context_object_name = "applications"
    paginate_by = 10

    def get_queryset(self):
        return LoanApplication.objects.filter(user=self.request.user).order_by(
            "-created_at"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Add statistics
        applications = self.get_queryset()
        context["total_applications"] = applications.count()
        context["active_loans"] = applications.filter(
            status=LoanApplication.Status.ACTIVE
        ).count()
        context["completed_loans"] = applications.filter(
            status=LoanApplication.Status.CLOSED
        ).count()

        return context


@login_required
def calculate_loan_view(request):
    """Calculate loan details using AJAX"""
    if request.method == "POST":
        loan_amount = Decimal(request.POST.get("loan_amount", "0"))
        loan_duration = int(request.POST.get("loan_duration", "1"))

        calculator = LoanCalculator()
        result = calculator.calculate(loan_amount, loan_duration)

        return JsonResponse(result)

    return JsonResponse({"error": "Invalid request method"})


@login_required
def upload_document_view(request, application_id):
    """Upload document for loan application"""
    application = get_object_or_404(
        LoanApplication, id=application_id, user=request.user
    )

    if request.method == "POST":
        form = LoanDocumentForm(request.POST, request.FILES)

        if form.is_valid():
            document = form.save(commit=False)
            document.loan_application = application
            document.filename = request.FILES["file"].name
            document.file_size = request.FILES["file"].size
            document.mime_type = request.FILES["file"].content_type

            # Validate file size
            if document.file_size > settings.MAX_UPLOAD_SIZE:
                return JsonResponse(
                    {
                        "success": False,
                        "error": f"File size exceeds maximum limit of {settings.MAX_UPLOAD_SIZE // (1024 * 1024)}MB",
                    }
                )

            document.save()

            return JsonResponse(
                {
                    "success": True,
                    "document": {
                        "id": document.id,
                        "document_type": document.get_document_type_display(),
                        "filename": document.filename,
                        "uploaded_at": document.uploaded_at.strftime("%Y-%m-%d %H:%M"),
                        "is_verified": document.is_verified,
                        "file_size_mb": document.get_file_size_mb(),
                    },
                }
            )

        return JsonResponse({"success": False, "errors": form.errors})

    return JsonResponse({"error": "Invalid request method"})


@login_required
@require_POST
def delete_document_view(request, application_id, document_id):
    """Delete document from loan application"""
    application = get_object_or_404(
        LoanApplication, id=application_id, user=request.user
    )
    document = get_object_or_404(
        LoanDocument, id=document_id, loan_application=application
    )

    # Delete file from storage
    if document.file and default_storage.exists(document.file.name):
        default_storage.delete(document.file.name)

    document.delete()

    return JsonResponse({"success": True})


@login_required
def add_collateral_view(request, application_id):
    """Add collateral to loan application"""
    application = get_object_or_404(
        LoanApplication, id=application_id, user=request.user
    )

    if request.method == "POST":
        form = LoanCollateralForm(request.POST, request.FILES)

        if form.is_valid():
            collateral = form.save(commit=False)
            collateral.loan_application = application
            collateral.save()

            return JsonResponse(
                {
                    "success": True,
                    "collateral": {
                        "id": collateral.id,
                        "collateral_type": collateral.get_collateral_type_display(),
                        "description": collateral.description,
                        "estimated_value": float(collateral.estimated_value),
                        "is_verified": collateral.is_verified,
                    },
                }
            )

        return JsonResponse({"success": False, "errors": form.errors})

    return JsonResponse({"error": "Invalid request method"})


@login_required
@require_POST
def delete_collateral_view(request, application_id, collateral_id):
    """Delete collateral from loan application"""
    application = get_object_or_404(
        LoanApplication, id=application_id, user=request.user
    )
    collateral = get_object_or_404(
        LoanCollateral, id=collateral_id, loan_application=application
    )

    # Delete files from storage
    if collateral.valuation_document and default_storage.exists(
        collateral.valuation_document.name
    ):
        default_storage.delete(collateral.valuation_document.name)

    if collateral.ownership_proof and default_storage.exists(
        collateral.ownership_proof.name
    ):
        default_storage.delete(collateral.ownership_proof.name)

    collateral.delete()

    return JsonResponse({"success": True})


@login_required
def add_guarantor_view(request, application_id):
    """Add guarantor to loan application"""
    application = get_object_or_404(
        LoanApplication, id=application_id, user=request.user
    )

    if request.method == "POST":
        form = LoanGuarantorForm(request.POST, request.FILES)

        if form.is_valid():
            guarantor = form.save(commit=False)
            guarantor.loan_application = application
            guarantor.save()

            return JsonResponse(
                {
                    "success": True,
                    "guarantor": {
                        "id": guarantor.id,
                        "name": guarantor.name,
                        "phone": guarantor.phone,
                        "relationship": guarantor.get_relationship_to_applicant_display(),
                        "is_verified": guarantor.is_verified,
                    },
                }
            )

        return JsonResponse({"success": False, "errors": form.errors})

    return JsonResponse({"error": "Invalid request method"})


@login_required
@require_POST
def delete_guarantor_view(request, application_id, guarantor_id):
    """Delete guarantor from loan application"""
    application = get_object_or_404(
        LoanApplication, id=application_id, user=request.user
    )
    guarantor = get_object_or_404(
        LoanGuarantor, id=guarantor_id, loan_application=application
    )

    # Delete files from storage
    if guarantor.guarantee_letter and default_storage.exists(
        guarantor.guarantee_letter.name
    ):
        default_storage.delete(guarantor.guarantee_letter.name)

    if guarantor.bank_statement and default_storage.exists(
        guarantor.bank_statement.name
    ):
        default_storage.delete(guarantor.bank_statement.name)

    if guarantor.id_copy and default_storage.exists(guarantor.id_copy.name):
        default_storage.delete(guarantor.id_copy.name)

    guarantor.delete()

    return JsonResponse({"success": True})


@login_required
def repayment_schedule_view(request, application_id):
    """View repayment schedule for approved loan"""
    application = get_object_or_404(
        LoanApplication,
        id=application_id,
        user=request.user,
        status__in=[LoanApplication.Status.APPROVED, LoanApplication.Status.ACTIVE],
    )

    repayments = application.repayment_schedule.all().order_by("installment_number")

    # Calculate totals
    total_paid = sum(r.amount_paid for r in repayments)
    total_due = sum(r.total_due for r in repayments)
    outstanding_balance = total_due - total_paid

    context = {
        "application": application,
        "repayments": repayments,
        "total_paid": total_paid,
        "total_due": total_due,
        "outstanding_balance": outstanding_balance,
    }

    return render(request, "berit/loans/repayment_schedule.html", context)


@login_required
def download_agreement_view(request, application_id):
    """Download loan agreement PDF"""
    application = get_object_or_404(
        LoanApplication,
        id=application_id,
        user=request.user,
        status=LoanApplication.Status.APPROVED,
    )

    try:
        # Generate PDF using WeasyPrint
        from django.template.loader import render_to_string
        from weasyprint import CSS, HTML

        html_content = render_to_string(
            "berit/loans/loan_agreement_pdf.html",
            {
                "application": application,
                "portal_settings": settings.PORTAL_SETTINGS,
            },
        )

        css = CSS(
            string="""
            @page {
                size: A4;
                margin: 2cm;
            }
            body {
                font-family: Arial, sans-serif;
                font-size: 12px;
                line-height: 1.4;
            }
            .header {
                text-align: center;
                margin-bottom: 30px;
            }
            .title {
                font-size: 20px;
                font-weight: bold;
                color: #1B3A6B;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 20px;
            }
            th, td {
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }
            th {
                background-color: #f5f5f5;
                font-weight: bold;
            }
        """
        )

        pdf = HTML(string=html_content).write_pdf(stylesheets=[css])

        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="loan_agreement_{application.reference_number}.pdf"'
        )
        return response

    except Exception as e:
        messages.error(request, f"Error generating PDF: {str(e)}")
        return redirect("loans:application_detail", pk=application_id)


@login_required
def loan_calculator_view(request):
    """Loan calculator page"""
    context = {
        "interest_rates": getattr(settings, "INTEREST_RATES", []),
        "loan_config": getattr(settings, "LOAN_CONFIG", {}),
    }

    return render(request, "berit/loans/calculator.html", context)
