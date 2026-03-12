# -*- coding: utf-8 -*-
"""
Enhanced loan application views with automatic Odoo synchronization
Handles multi-step wizard, document uploads, and real-time sync to Odoo backend
"""

import json
import logging
import uuid
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.core.mail import send_mail
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import DetailView, ListView, TemplateView

from apps.accounts.models import User

from .enhanced_tasks import send_application_confirmation_email, sync_loan_to_odoo_async
from .models import (
    LoanApplication,
    LoanCollateral,
    LoanDocument,
    LoanGuarantor,
    RepaymentSchedule,
)
from .sync.perfect_sync import PerfectOdooSync
from .sync.webhook_models import SyncEvent
from .utils import LoanCalculator

logger = logging.getLogger(__name__)


class ModernLoanWizardView(TemplateView):
    """Modern multi-step loan application wizard"""

    template_name = "loans/modern_wizard.html"

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Apply for Loan"
        context["user"] = self.request.user
        return context


@login_required
@require_http_methods(["POST"])
def submit_loan_application(request):
    """
    Handle loan application submission with document uploads, inline
    collaterals, inline guarantors, and automatic Odoo synchronisation.
    """
    try:
        with transaction.atomic():
            # ── Extract scalar form fields ─────────────────────────────
            loan_amount = Decimal(request.POST.get("loan_amount") or 0)
            loan_duration_months = int(request.POST.get("loan_duration_months") or 0)
            loan_purpose = request.POST.get("loan_purpose", "").strip()
            employment_type = request.POST.get("employment_type", "").strip()
            first_name = request.POST.get("first_name", "").strip()
            last_name = request.POST.get("last_name", "").strip()
            national_id = request.POST.get("national_id", "").strip()
            phone_number = request.POST.get("phone_number", "").strip()
            email = request.POST.get("email", "").strip()
            employer_name = request.POST.get("employer_name", "").strip()
            job_title = request.POST.get("job_title", "").strip()
            monthly_income = Decimal(request.POST.get("monthly_income") or 0)
            employment_duration_years = float(
                request.POST.get("employment_duration_years") or 0
            )

            # ── Validate required fields ───────────────────────────────
            validation_errors = validate_loan_application_data(
                loan_amount=loan_amount,
                loan_duration_months=loan_duration_months,
                loan_purpose=loan_purpose,
                employment_type=employment_type,
                national_id=national_id,
                phone_number=phone_number,
                monthly_income=monthly_income,
                employment_duration_years=employment_duration_years,
            )

            if validation_errors:
                return JsonResponse(
                    {"success": False, "errors": validation_errors}, status=400
                )

            # ── Create the LoanApplication record ─────────────────────
            # NOTE: The model field is loan_duration (not loan_duration_months).
            # generate_reference_number is an instance method; the model's save()
            # already calls it, but we pass a dummy value here so the field
            # validation passes — save() will overwrite it.
            application = LoanApplication(
                user=request.user,
                loan_amount=loan_amount,
                loan_duration=loan_duration_months,  # model field name
                loan_purpose=loan_purpose,
                employment_type=employment_type,
                status=LoanApplication.Status.SUBMITTED,
                submitted_at=timezone.now(),
            )
            # generate_reference_number() is defined on the instance;
            # model.save() calls it automatically, so just save directly.
            application.save()

            logger.info(f"Created loan application {application.id}")

            # ── Calculate and persist loan financial details ───────────
            calculator = LoanCalculator()
            loan_details = calculator.calculate(
                loan_amount, loan_duration_months
            )  # duration in months

            application.interest_rate = loan_details["interest_rate"]
            application.monthly_repayment = Decimal(
                str(loan_details["monthly_repayment"])
            )
            application.total_repayable = Decimal(str(loan_details["total_repayable"]))
            application.legal_fee = Decimal(str(loan_details["legal_fee"]))
            application.collateral_required = Decimal(
                str(loan_details["collateral_required"])
            )
            application.save()

            # ── Handle primary document uploads (id_copy, payslip, …) ─
            handle_document_uploads(request, application)

            # ── Persist employment details ─────────────────────────────
            if employer_name or job_title:
                application.employment_data = {
                    "employer_name": employer_name,
                    "job_title": job_title,
                    "monthly_income": str(monthly_income),
                    "employment_duration_years": employment_duration_years,
                }
                application.save()

            # ── Save inline collaterals from wizard ────────────────────
            collaterals_count = int(request.POST.get("collaterals_count") or 0)
            for i in range(collaterals_count):
                try:
                    col_type = request.POST.get(f"collateral_{i}_type", "")
                    col_desc = request.POST.get(f"collateral_{i}_description", "")
                    col_value_raw = (
                        request.POST.get(f"collateral_{i}_estimated_value") or 0
                    )
                    col_value = Decimal(str(col_value_raw))
                    col_val_date = request.POST.get(
                        f"collateral_{i}_valuation_date", ""
                    )
                    col_location = request.POST.get(f"collateral_{i}_location", "")

                    if (
                        not col_type
                        or not col_desc
                        or col_value <= 0
                        or not col_val_date
                    ):
                        logger.warning(f"Skipping incomplete collateral {i}")
                        continue

                    collateral = LoanCollateral(
                        loan_application=application,
                        collateral_type=col_type,
                        description=col_desc,
                        estimated_value=col_value,
                        valuation_date=col_val_date,
                        location=col_location,
                    )

                    ownership_file = request.FILES.get(
                        f"collateral_{i}_ownership_proof"
                    )
                    if ownership_file:
                        collateral.ownership_proof = ownership_file

                    valuation_file = request.FILES.get(
                        f"collateral_{i}_valuation_document"
                    )
                    if valuation_file:
                        collateral.valuation_document = valuation_file

                    collateral.save()
                    logger.info(
                        f"Saved collateral {i} for application {application.id}"
                    )
                except Exception as e:
                    logger.error(f"Error saving collateral {i}: {e}")

            # ── Save inline guarantors from wizard ─────────────────────
            guarantors_count = int(request.POST.get("guarantors_count") or 0)
            for i in range(guarantors_count):
                try:
                    g_name = request.POST.get(f"guarantor_{i}_name", "").strip()
                    g_id = request.POST.get(f"guarantor_{i}_id_number", "").strip()
                    g_phone = request.POST.get(f"guarantor_{i}_phone", "").strip()
                    g_email = request.POST.get(f"guarantor_{i}_email", "").strip()
                    g_rel = request.POST.get(
                        f"guarantor_{i}_relationship_to_applicant", ""
                    )
                    g_occ = request.POST.get(f"guarantor_{i}_occupation", "")
                    g_income_raw = (
                        request.POST.get(f"guarantor_{i}_monthly_income") or None
                    )
                    g_income = Decimal(str(g_income_raw)) if g_income_raw else None
                    g_address = request.POST.get(
                        f"guarantor_{i}_employer_address", ""
                    ).strip()

                    if not g_name or not g_id or not g_phone or not g_address:
                        logger.warning(f"Skipping incomplete guarantor {i}")
                        continue

                    # guarantee_letter and id_copy are required by the model
                    g_id_copy_file = request.FILES.get(f"guarantor_{i}_id_copy")
                    g_guarantee_file = request.FILES.get(
                        f"guarantor_{i}_guarantee_letter"
                    )

                    if not g_id_copy_file or not g_guarantee_file:
                        logger.warning(
                            f"Skipping guarantor {i} — missing required documents"
                        )
                        continue

                    guarantor = LoanGuarantor(
                        loan_application=application,
                        name=g_name,
                        id_number=g_id,
                        phone=g_phone,
                        email=g_email,
                        relationship_to_applicant=g_rel,
                        occupation=g_occ,
                        monthly_income=g_income,
                        employer_address=g_address,
                        id_copy=g_id_copy_file,
                        guarantee_letter=g_guarantee_file,
                    )

                    g_bank_file = request.FILES.get(f"guarantor_{i}_bank_statement")
                    if g_bank_file:
                        guarantor.bank_statement = g_bank_file

                    guarantor.save()
                    logger.info(f"Saved guarantor {i} for application {application.id}")
                except Exception as e:
                    logger.error(f"Error saving guarantor {i}: {e}")

            # ── Generate repayment schedule ────────────────────────────
            create_repayment_schedule(application)

            # ── Log sync event ─────────────────────────────────────────
            try:
                sync_event = SyncEvent.objects.create(
                    event_type=SyncEvent.EventType.LOAN_CREATED,
                    direction=SyncEvent.Direction.DJANGO_TO_ODOO,
                    status=SyncEvent.Status.PENDING,
                    loan_application_id=application.id,
                    payload={
                        "application_id": str(application.id),
                        "reference_number": application.reference_number,
                        "loan_amount": float(loan_amount),
                        "duration_months": loan_duration_months,
                        "interest_rate": float(application.interest_rate),
                        "monthly_payment": float(application.monthly_repayment),
                        "user_email": request.user.email,
                        "user_phone": phone_number,
                    },
                )
                logger.info(
                    f"Created sync event {sync_event.id} for application {application.id}"
                )
            except Exception as e:
                logger.error(f"Error creating sync event: {e}")
                sync_event = None

            # ── Queue Celery sync task ─────────────────────────────────
            task_id = None
            try:
                task = sync_loan_to_odoo_async.delay(str(application.id))
                task_id = task.id
                logger.info(
                    f"Queued Odoo sync task {task_id} for application {application.id}"
                )
            except Exception as e:
                logger.error(f"Error queuing sync task: {e}")

            # ── Send confirmation email (best-effort) ──────────────────
            try:
                send_application_confirmation_email.delay(
                    application_id=str(application.id),
                    email=request.user.email,
                )
            except Exception as e:
                logger.error(f"Error queuing confirmation email: {e}")

            # ── Return success response ────────────────────────────────
            detail_url = reverse_lazy("loans:application_detail", args=[application.id])
            return JsonResponse(
                {
                    "success": True,
                    "message": "Application submitted successfully!",
                    "application_id": str(application.id),
                    "reference_number": application.reference_number,
                    "sync_task_id": task_id,
                    "redirect_url": str(detail_url),
                },
                status=201,
            )

    except ValueError as e:
        logger.error(f"Validation error in loan submission: {e}")
        return JsonResponse(
            {"success": False, "message": f"Invalid data: {e}"}, status=400
        )
    except Exception as e:
        logger.error(f"Error submitting loan application: {e}", exc_info=True)
        return JsonResponse(
            {
                "success": False,
                "message": "Failed to submit application. Please try again later.",
            },
            status=500,
        )


@login_required
@require_http_methods(["GET"])
def get_loan_sync_status(request, application_id):
    """Get real-time sync status for a loan application"""
    try:
        application = LoanApplication.objects.get(id=application_id, user=request.user)

        # Get latest sync event — SyncEvent uses loan_application_id (UUIDField)
        sync_event = (
            SyncEvent.objects.filter(loan_application_id=application_id)
            .order_by("-created_at")
            .first()
        )

        # The model field is odoo_application_id (not odoo_record_id)
        odoo_synced = application.odoo_application_id is not None

        return JsonResponse(
            {
                "success": True,
                "data": {
                    "application_id": str(application.id),
                    "reference_number": application.reference_number,
                    "status": application.status,
                    "odoo_synced": odoo_synced,
                    "odoo_record_id": application.odoo_application_id,
                    "sync_status": sync_event.status if sync_event else "pending",
                    "last_sync_at": sync_event.created_at.isoformat()
                    if sync_event
                    else None,
                },
            }
        )

    except LoanApplication.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Application not found"}, status=404
        )
    except Exception as e:
        logger.error(f"Error getting sync status: {str(e)}")
        return JsonResponse(
            {"success": False, "message": "Error retrieving sync status"},
            status=500,
        )


@login_required
@require_http_methods(["GET"])
def get_dashboard_sync_status(request):
    """Get sync status summary for dashboard"""
    try:
        user_applications = LoanApplication.objects.filter(
            user=request.user
        ).values_list("id", flat=True)

        pending_syncs = SyncEvent.objects.filter(
            loan_application_id__in=user_applications,
            status__in=[SyncEvent.Status.PENDING, SyncEvent.Status.RETRY],
        ).count()

        failed_syncs = SyncEvent.objects.filter(
            loan_application_id__in=user_applications,
            status=SyncEvent.Status.FAILED,
        ).count()

        return JsonResponse(
            {
                "success": True,
                "data": {
                    "pending_sync_count": pending_syncs,
                    "failed_sync_count": failed_syncs,
                    "total_applications": user_applications.count(),
                },
            }
        )
    except Exception as e:
        logger.error(f"Error getting dashboard sync status: {str(e)}")
        return JsonResponse(
            {"success": False, "message": "Error retrieving sync status"},
            status=500,
        )


class ApplicationSuccessView(TemplateView):
    """Shown after a successful loan application submission."""

    template_name = "loans/application_success.html"

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Application Submitted"
        return context


class ApplicationDetailView(DetailView):
    """View application details with sync status"""

    model = LoanApplication
    template_name = "loans/application_detail.html"
    context_object_name = "application"

    @method_decorator(login_required)
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return LoanApplication.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        application = self.get_object()

        # Get sync events — SyncEvent uses loan_application_id (UUIDField)
        sync_events = SyncEvent.objects.filter(
            loan_application_id=application.id
        ).order_by("-created_at")[:10]

        # Get documents
        documents = LoanDocument.objects.filter(loan_application=application)

        # Get repayment schedule
        repayments = RepaymentSchedule.objects.filter(
            loan_application=application
        ).order_by("due_date")

        # Calculate stats
        total_due = sum(r.total_due for r in repayments)
        total_paid = sum(r.amount_paid for r in repayments)
        outstanding = total_due - total_paid

        context.update(
            {
                "sync_events": sync_events,
                "documents": documents,
                "repayments": repayments,
                "total_due": total_due,
                "total_paid": total_paid,
                "outstanding": outstanding,
                "odoo_synced": application.odoo_application_id is not None,
                "page_title": f"Application {application.reference_number}",
            }
        )

        return context


class ApplicationListView(ListView):
    """List all user's loan applications"""

    model = LoanApplication
    template_name = "loans/loanapplication_list.html"
    context_object_name = "applications"
    paginate_by = 20

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_queryset(self):
        queryset = LoanApplication.objects.filter(user=self.request.user).order_by(
            "-created_at"
        )

        # Filter by status if provided
        status = self.request.GET.get("status")
        if status:
            queryset = queryset.filter(status=status)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = LoanApplication.Status.choices
        context["current_status"] = self.request.GET.get("status")
        context["page_title"] = "My Loan Applications"
        return context


# Helper Functions


def validate_loan_application_data(**kwargs) -> dict:
    """Validate loan application data"""
    errors = {}

    loan_amount = kwargs.get("loan_amount", 0)
    if not loan_amount or loan_amount < 1000:
        errors["loan_amount"] = "Loan amount must be at least KES 1,000"
    if loan_amount > 10000000:
        errors["loan_amount"] = "Loan amount cannot exceed KES 10,000,000"

    loan_duration = kwargs.get("loan_duration_months", 0)
    if not loan_duration or loan_duration < 1 or loan_duration > 60:
        errors["loan_duration_months"] = "Duration must be between 1 and 60 months"

    loan_purpose = kwargs.get("loan_purpose", "").strip()
    if not loan_purpose or len(loan_purpose) < 10:
        errors["loan_purpose"] = (
            "Please provide a detailed loan purpose (min 10 characters)"
        )

    employment_type = kwargs.get("employment_type", "")
    if not employment_type:
        errors["employment_type"] = "Employment type is required"

    national_id = kwargs.get("national_id", "").strip()
    if not national_id or len(national_id) < 5:
        errors["national_id"] = "Valid national ID is required"

    phone_number = kwargs.get("phone_number", "").strip()
    if not phone_number or len(phone_number) < 9:
        errors["phone_number"] = "Valid phone number is required"

    monthly_income = kwargs.get("monthly_income", 0)
    if not monthly_income or monthly_income <= 0:
        errors["monthly_income"] = "Monthly income is required"

    employment_duration = kwargs.get("employment_duration_years", 0)
    if employment_duration < 0:
        errors["employment_duration_years"] = "Employment duration cannot be negative"

    return errors


def handle_document_uploads(request, application):
    """Handle document file uploads for loan application"""
    document_types = {
        "id_copy": "National ID Copy",
        "payslip": "Payslip",
        "kra_pin": "KRA PIN Certificate",
        "bank_statement": "Bank Statement",
        "passport_photo": "Passport Photo",
    }

    for field_name, doc_type_label in document_types.items():
        if field_name in request.FILES:
            file = request.FILES.get(field_name)
            if file:
                try:
                    # Validate file size (5MB max)
                    if file.size > 5 * 1024 * 1024:
                        logger.warning(
                            f"File {field_name} too large: {file.size} bytes"
                        )
                        continue

                    # LoanDocument requires filename, file_size, and mime_type
                    import mimetypes

                    mime_type, _ = mimetypes.guess_type(file.name)

                    # Create document record — handle unique_together gracefully
                    LoanDocument.objects.update_or_create(
                        loan_application=application,
                        document_type=field_name,
                        defaults={
                            "file": file,
                            "filename": file.name,
                            "file_size": file.size,
                            "mime_type": mime_type or "",
                        },
                    )

                    logger.info(
                        f"Uploaded document {field_name} for application {application.id}"
                    )

                except Exception as e:
                    logger.error(f"Error uploading document {field_name}: {str(e)}")


def create_repayment_schedule(application):
    """Create repayment schedule for loan application"""
    try:
        from dateutil.relativedelta import relativedelta

        # monthly_repayment and interest_rate are already persisted on the application
        loan_amount = application.loan_amount
        duration_months = application.loan_duration  # model field name
        interest_rate = application.interest_rate  # monthly flat rate (%)

        start_date = (
            application.submitted_at.date()
            if application.submitted_at
            else timezone.now().date()
        )

        principal_per_month = loan_amount / Decimal(str(duration_months))
        monthly_interest = loan_amount * (interest_rate / Decimal("100"))

        for month in range(1, duration_months + 1):
            due_date = start_date + relativedelta(months=month)

            RepaymentSchedule.objects.get_or_create(
                loan_application=application,
                installment_number=month,
                defaults={
                    "due_date": due_date,
                    "principal_amount": principal_per_month,
                    "interest_amount": monthly_interest,
                    # total_due is computed by RepaymentSchedule.save()
                    "amount_paid": Decimal("0"),
                    "status": RepaymentSchedule.Status.PENDING,
                },
            )

        logger.info(f"Created repayment schedule for application {application.id}")

    except Exception as e:
        logger.error(f"Error creating repayment schedule: {str(e)}")


def calculate_loan_metrics(application):
    """Calculate loan metrics for display"""
    try:
        repayments = RepaymentSchedule.objects.filter(loan_application=application)

        total_due = sum(r.total_due for r in repayments)
        total_paid = sum(r.amount_paid for r in repayments)
        outstanding = total_due - total_paid

        paid_count = repayments.filter(status="paid").count()
        pending_count = repayments.filter(status="pending").count()

        return {
            "total_due": total_due,
            "total_paid": total_paid,
            "outstanding": outstanding,
            "paid_count": paid_count,
            "pending_count": pending_count,
            "completion_percentage": int(
                (total_paid / total_due * 100) if total_due > 0 else 0
            ),
        }

    except Exception as e:
        logger.error(f"Error calculating loan metrics: {str(e)}")
        return {
            "total_due": 0,
            "total_paid": 0,
            "outstanding": 0,
            "paid_count": 0,
            "pending_count": 0,
            "completion_percentage": 0,
        }
