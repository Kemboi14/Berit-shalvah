# -*- coding: utf-8 -*-
"""
Dashboard views for different user types
"""

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.generic import TemplateView

from apps.accounts.models import ClientProfile, User
from apps.loans.models import LoanApplication, RepaymentSchedule


@login_required
def client_dashboard_view(request):
    """Client dashboard view"""
    user = request.user

    # Get user's profile
    profile = user.get_client_profile()

    # Loan statistics
    loan_applications = LoanApplication.objects.filter(user=user)
    total_applications = loan_applications.count()
    active_loans = loan_applications.filter(
        status=LoanApplication.Status.ACTIVE
    ).count()
    completed_loans = loan_applications.filter(
        status=LoanApplication.Status.CLOSED
    ).count()

    # Recent applications
    recent_applications = loan_applications.order_by("-created_at")[:5]

    # Active loans and repayments
    active_loan_applications = loan_applications.filter(
        status=LoanApplication.Status.ACTIVE
    )
    upcoming_repayments = []

    for loan in active_loan_applications:
        next_repayment = (
            loan.repayment_schedule.filter(status=RepaymentSchedule.Status.PENDING)
            .order_by("due_date")
            .first()
        )

        if next_repayment:
            upcoming_repayments.append(
                {
                    "loan": loan,
                    "repayment": next_repayment,
                    "days_until_due": (
                        next_repayment.due_date - timezone.now().date()
                    ).days,
                }
            )

    # Sort by due date
    upcoming_repayments.sort(key=lambda x: x["days_until_due"])

    # Calculate totals
    total_borrowed = sum(
        app.loan_amount
        for app in loan_applications.filter(
            status__in=[LoanApplication.Status.ACTIVE, LoanApplication.Status.CLOSED]
        )
    )

    total_repaid = 0
    for loan in active_loan_applications:
        total_repaid += sum(r.amount_paid for r in loan.repayment_schedule.all())

    # Profile completion
    completion_percentage = 0
    if profile:
        completion_percentage = profile.get_completion_percentage()

    context = {
        "profile": profile,
        "completion_percentage": completion_percentage,
        "total_applications": total_applications,
        "active_loans": active_loans,
        "completed_loans": completed_loans,
        "recent_applications": recent_applications,
        "upcoming_repayments": upcoming_repayments[:3],  # Show next 3
        "total_borrowed": total_borrowed,
        "total_repaid": total_repaid,
        "outstanding_balance": total_borrowed - total_repaid,
    }

    return render(request, "berit/dashboard/client_dashboard.html", context)


@login_required
def staff_dashboard_view(request):
    """Staff dashboard view"""
    if not request.user.is_staff:
        return render(request, "berit/errors/403.html")

    # Overall statistics
    total_users = User.objects.filter(user_type=User.UserType.CLIENT).count()
    total_applications = LoanApplication.objects.count()

    # Applications by status
    applications_by_status = (
        LoanApplication.objects.values("status")
        .annotate(count=Count("id"))
        .order_by("status")
    )

    # Recent applications
    recent_applications = LoanApplication.objects.order_by("-created_at")[:10]

    # Pending verifications
    pending_verifications = LoanApplication.objects.filter(
        status=LoanApplication.Status.UNDER_REVIEW
    ).order_by("-submitted_at")[:10]

    # Today's activity
    today = timezone.now().date()
    today_applications = LoanApplication.objects.filter(created_at__date=today).count()
    today_approvals = LoanApplication.objects.filter(approved_at__date=today).count()

    # Monthly statistics
    this_month = timezone.now().replace(day=1)
    monthly_applications = LoanApplication.objects.filter(
        created_at__gte=this_month
    ).count()
    monthly_approvals = LoanApplication.objects.filter(
        approved_at__gte=this_month
    ).count()

    # Loan portfolio value
    active_loans = LoanApplication.objects.filter(status=LoanApplication.Status.ACTIVE)
    portfolio_value = sum(loan.loan_amount for loan in active_loans)

    # Overdue repayments
    overdue_repayments = RepaymentSchedule.objects.filter(
        status=RepaymentSchedule.Status.OVERDUE
    ).count()

    context = {
        "total_users": total_users,
        "total_applications": total_applications,
        "applications_by_status": applications_by_status,
        "recent_applications": recent_applications,
        "pending_verifications": pending_verifications,
        "today_applications": today_applications,
        "today_approvals": today_approvals,
        "monthly_applications": monthly_applications,
        "monthly_approvals": monthly_approvals,
        "portfolio_value": portfolio_value,
        "overdue_repayments": overdue_repayments,
    }

    return render(request, "berit/dashboard/staff_dashboard.html", context)


@login_required
def admin_dashboard_view(request):
    """Admin dashboard view"""
    if not request.user.is_superuser:
        return render(request, "berit/errors/403.html")

    # Build staff context directly (do not call the view function — it returns
    # an HttpResponse which has no .context_data attribute).
    total_users = User.objects.filter(user_type=User.UserType.CLIENT).count()
    total_applications = LoanApplication.objects.count()

    applications_by_status = (
        LoanApplication.objects.values("status")
        .annotate(count=Count("id"))
        .order_by("status")
    )

    recent_applications = LoanApplication.objects.order_by("-created_at")[:10]

    pending_verifications = LoanApplication.objects.filter(
        status=LoanApplication.Status.UNDER_REVIEW
    ).order_by("-submitted_at")[:10]

    today = timezone.now().date()
    today_applications = LoanApplication.objects.filter(created_at__date=today).count()
    today_approvals = LoanApplication.objects.filter(approved_at__date=today).count()

    this_month = timezone.now().replace(day=1)
    monthly_applications = LoanApplication.objects.filter(
        created_at__gte=this_month
    ).count()
    monthly_approvals = LoanApplication.objects.filter(
        approved_at__gte=this_month
    ).count()

    active_loans = LoanApplication.objects.filter(status=LoanApplication.Status.ACTIVE)
    portfolio_value = sum(loan.loan_amount for loan in active_loans)

    overdue_repayments = RepaymentSchedule.objects.filter(
        status=RepaymentSchedule.Status.OVERDUE
    ).count()

    # Admin-specific additions
    total_staff = User.objects.filter(
        user_type__in=[User.UserType.STAFF, User.UserType.ADMIN]
    ).count()

    from django.db import connection

    db_status = "Healthy" if connection.is_usable() else "Unhealthy"

    recent_users = User.objects.filter(user_type=User.UserType.CLIENT).order_by(
        "-date_joined"
    )[:10]

    try:
        from apps.documents.models import UploadedDocument

        total_documents = UploadedDocument.objects.count()
        documents_size = sum(doc.file_size for doc in UploadedDocument.objects.all())
    except Exception:
        total_documents = 0
        documents_size = 0

    context = {
        "total_users": total_users,
        "total_applications": total_applications,
        "applications_by_status": applications_by_status,
        "recent_applications": recent_applications,
        "pending_verifications": pending_verifications,
        "today_applications": today_applications,
        "today_approvals": today_approvals,
        "monthly_applications": monthly_applications,
        "monthly_approvals": monthly_approvals,
        "portfolio_value": portfolio_value,
        "overdue_repayments": overdue_repayments,
        "total_staff": total_staff,
        "db_status": db_status,
        "recent_users": recent_users,
        "total_documents": total_documents,
        "documents_size_mb": round(documents_size / (1024 * 1024), 2),
    }

    return render(request, "berit/dashboard/admin_dashboard.html", context)


class DashboardView(LoginRequiredMixin, TemplateView):
    """Main dashboard view that routes to appropriate dashboard"""

    template_name = "berit/dashboard/dashboard.html"

    def get_template_names(self):
        """Return appropriate template based on user type"""
        user = self.request.user

        if user.is_superuser:
            return ["berit/dashboard/admin_dashboard.html"]
        elif user.is_staff:
            return ["berit/dashboard/staff_dashboard.html"]
        else:
            return ["berit/dashboard/client_dashboard.html"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        if user.is_superuser:
            # Admin dashboard context
            return self.get_admin_context(context)
        elif user.is_staff:
            # Staff dashboard context
            return self.get_staff_context(context)
        else:
            # Client dashboard context
            return self.get_client_context(context)

    def get_client_context(self, context):
        """Get client dashboard context"""
        user = self.request.user

        # Get user's profile
        profile = user.get_client_profile()

        # Loan statistics
        loan_applications = LoanApplication.objects.filter(user=user)
        total_applications = loan_applications.count()
        active_loans = loan_applications.filter(
            status=LoanApplication.Status.ACTIVE
        ).count()
        completed_loans = loan_applications.filter(
            status=LoanApplication.Status.CLOSED
        ).count()

        # Recent applications
        recent_applications = loan_applications.order_by("-created_at")[:5]

        # Active loans and repayments
        active_loan_applications = loan_applications.filter(
            status=LoanApplication.Status.ACTIVE
        )
        upcoming_repayments = []

        for loan in active_loan_applications:
            next_repayment = (
                loan.repayment_schedule.filter(status=RepaymentSchedule.Status.PENDING)
                .order_by("due_date")
                .first()
            )

            if next_repayment:
                upcoming_repayments.append(
                    {
                        "loan": loan,
                        "repayment": next_repayment,
                        "days_until_due": (
                            next_repayment.due_date - timezone.now().date()
                        ).days,
                    }
                )

        # Sort by due date
        upcoming_repayments.sort(key=lambda x: x["days_until_due"])

        # Calculate totals
        total_borrowed = sum(
            app.loan_amount
            for app in loan_applications.filter(
                status__in=[
                    LoanApplication.Status.ACTIVE,
                    LoanApplication.Status.CLOSED,
                ]
            )
        )

        total_repaid = 0
        for loan in active_loan_applications:
            total_repaid += sum(r.amount_paid for r in loan.repayment_schedule.all())

        # Profile completion
        completion_percentage = 0
        if profile:
            completion_percentage = profile.get_completion_percentage()

        context.update(
            {
                "profile": profile,
                "completion_percentage": completion_percentage,
                "total_applications": total_applications,
                "active_loans": active_loans,
                "completed_loans": completed_loans,
                "recent_applications": recent_applications,
                "upcoming_repayments": upcoming_repayments[:3],
                "total_borrowed": total_borrowed,
                "total_repaid": total_repaid,
                "outstanding_balance": total_borrowed - total_repaid,
            }
        )

        return context

    def get_staff_context(self, context):
        """Get staff dashboard context"""
        # Overall statistics
        total_users = User.objects.filter(user_type=User.UserType.CLIENT).count()
        total_applications = LoanApplication.objects.count()

        # Applications by status
        applications_by_status = (
            LoanApplication.objects.values("status")
            .annotate(count=Count("id"))
            .order_by("status")
        )

        # Recent applications
        recent_applications = LoanApplication.objects.order_by("-created_at")[:10]

        # Pending verifications
        pending_verifications = LoanApplication.objects.filter(
            status=LoanApplication.Status.UNDER_REVIEW
        ).order_by("-submitted_at")[:10]

        # Today's activity
        today = timezone.now().date()
        today_applications = LoanApplication.objects.filter(
            created_at__date=today
        ).count()
        today_approvals = LoanApplication.objects.filter(
            approved_at__date=today
        ).count()

        # Monthly statistics
        this_month = timezone.now().replace(day=1)
        monthly_applications = LoanApplication.objects.filter(
            created_at__gte=this_month
        ).count()
        monthly_approvals = LoanApplication.objects.filter(
            approved_at__gte=this_month
        ).count()

        # Loan portfolio value
        active_loans = LoanApplication.objects.filter(
            status=LoanApplication.Status.ACTIVE
        )
        portfolio_value = sum(loan.loan_amount for loan in active_loans)

        # Overdue repayments
        overdue_repayments = RepaymentSchedule.objects.filter(
            status=RepaymentSchedule.Status.OVERDUE
        ).count()

        context.update(
            {
                "total_users": total_users,
                "total_applications": total_applications,
                "applications_by_status": applications_by_status,
                "recent_applications": recent_applications,
                "pending_verifications": pending_verifications,
                "today_applications": today_applications,
                "today_approvals": today_approvals,
                "monthly_applications": monthly_applications,
                "monthly_approvals": monthly_approvals,
                "portfolio_value": portfolio_value,
                "overdue_repayments": overdue_repayments,
            }
        )

        return context

    def get_admin_context(self, context):
        """Get admin dashboard context"""
        # Get staff context first
        self.get_staff_context(context)

        # Additional admin-specific data
        total_staff = User.objects.filter(
            user_type__in=[User.UserType.STAFF, User.UserType.ADMIN]
        ).count()

        # System health
        from django.db import connection

        db_status = "Healthy" if connection.is_usable() else "Unhealthy"

        # Recent user registrations
        recent_users = User.objects.filter(user_type=User.UserType.CLIENT).order_by(
            "-date_joined"
        )[:10]

        # Document statistics
        try:
            from apps.documents.models import UploadedDocument

            total_documents = UploadedDocument.objects.count()
            documents_size = sum(
                doc.file_size for doc in UploadedDocument.objects.all()
            )
        except:
            total_documents = 0
            documents_size = 0

        context.update(
            {
                "total_staff": total_staff,
                "db_status": db_status,
                "recent_users": recent_users,
                "total_documents": total_documents,
                "documents_size_mb": round(documents_size / (1024 * 1024), 2),
            }
        )

        return context


@login_required
def dashboard_stats_view(request):
    """AJAX endpoint for dashboard statistics"""
    user = request.user

    if user.is_superuser:
        # Admin stats
        stats = {
            "total_users": User.objects.filter(user_type=User.UserType.CLIENT).count(),
            "total_applications": LoanApplication.objects.count(),
            "active_loans": LoanApplication.objects.filter(
                status=LoanApplication.Status.ACTIVE
            ).count(),
            "portfolio_value": float(
                sum(
                    loan.loan_amount
                    for loan in LoanApplication.objects.filter(
                        status=LoanApplication.Status.ACTIVE
                    )
                )
            ),
        }
    elif user.is_staff:
        # Staff stats
        stats = {
            "total_applications": LoanApplication.objects.count(),
            "pending_reviews": LoanApplication.objects.filter(
                status=LoanApplication.Status.UNDER_REVIEW
            ).count(),
            "today_applications": LoanApplication.objects.filter(
                created_at__date=timezone.now().date()
            ).count(),
            "portfolio_value": float(
                sum(
                    loan.loan_amount
                    for loan in LoanApplication.objects.filter(
                        status=LoanApplication.Status.ACTIVE
                    )
                )
            ),
        }
    else:
        # Client stats
        user_applications = LoanApplication.objects.filter(user=user)
        stats = {
            "total_applications": user_applications.count(),
            "active_loans": user_applications.filter(
                status=LoanApplication.Status.ACTIVE
            ).count(),
            "upcoming_payments": RepaymentSchedule.objects.filter(
                loan_application__user=user,
                status=RepaymentSchedule.Status.PENDING,
                due_date__lte=timezone.now().date() + timedelta(days=7),
            ).count(),
            "completion_percentage": user.get_client_profile().get_completion_percentage()
            if user.get_client_profile()
            else 0,
        }

    return JsonResponse(stats)
