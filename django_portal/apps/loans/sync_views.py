# -*- coding: utf-8 -*-
"""
Enhanced Django views with real-time Odoo synchronization
"""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .enhanced_tasks import sync_loan_application
from .models import LoanApplication
from .odoo_sync import EnhancedOdooIntegration

logger = logging.getLogger(__name__)


@login_required
def sync_application_to_odoo(request, application_id):
    """Sync a single application to Odoo"""
    application = get_object_or_404(
        LoanApplication, id=application_id, user=request.user
    )

    if application.odoo_application_id:
        messages.info(request, "This application is already synced with Odoo.")
        return redirect("loans:application_detail", pk=application_id)

    try:
        # Queue sync task
        sync_loan_application.delay(application_id)
        messages.success(request, "Application queued for synchronization with Odoo.")

    except Exception as e:
        logger.error(
            f"Error queueing sync for {application.reference_number}: {str(e)}"
        )
        messages.error(request, "Failed to queue synchronization. Please try again.")

    return redirect("loans:application_detail", pk=application_id)


@login_required
@require_POST
def force_sync_application(request, application_id):
    """Force immediate sync of application to Odoo"""
    application = get_object_or_404(
        LoanApplication, id=application_id, user=request.user
    )

    try:
        integration = EnhancedOdooIntegration()

        if not application.odoo_application_id:
            # Create new application in Odoo
            odoo_id = integration.create_loan_application(application)
            application.odoo_application_id = odoo_id
            application.save()

            messages.success(
                request, f"Application successfully synced to Odoo (ID: {odoo_id})"
            )
        else:
            # Update existing application
            integration.update_loan_status(
                application.odoo_application_id,
                integration._map_django_status_to_odoo(application.status),
            )

            messages.success(request, "Application status updated in Odoo")

    except Exception as e:
        logger.error(f"Error force syncing {application.reference_number}: {str(e)}")
        messages.error(request, f"Sync failed: {str(e)}")

    return redirect("loans:application_detail", pk=application_id)


@login_required
def sync_status_from_odoo(request, application_id):
    """Sync application status from Odoo"""
    application = get_object_or_404(
        LoanApplication, id=application_id, user=request.user
    )

    if not application.odoo_application_id:
        messages.warning(request, "This application is not synced with Odoo yet.")
        return redirect("loans:application_detail", pk=application_id)

    try:
        integration = EnhancedOdooIntegration()
        odoo_data = integration.get_loan_status(application.odoo_application_id)

        if odoo_data:
            odoo_status = odoo_data.get("state")
            django_status = integration._map_odoo_status(odoo_status)

            if django_status and application.status != django_status:
                old_status = application.status
                application.status = django_status

                # Update dates based on status
                if django_status == LoanApplication.Status.APPROVED:
                    application.approved_at = timezone.now()
                elif django_status == LoanApplication.Status.DISBURSED:
                    application.disbursed_at = timezone.now()

                application.save()

                messages.success(
                    request, f"Status updated from {old_status} to {django_status}"
                )
            else:
                messages.info(request, "Status is already up to date")
        else:
            messages.warning(request, "Could not retrieve status from Odoo")

    except Exception as e:
        logger.error(
            f"Error syncing status from Odoo for {application.reference_number}: {str(e)}"
        )
        messages.error(request, f"Status sync failed: {str(e)}")

    return redirect("loans:application_detail", pk=application_id)


@login_required
def sync_all_applications(request):
    """Sync all user applications to Odoo"""
    applications = LoanApplication.objects.filter(
        user=request.user, odoo_application_id__isnull=True
    ).exclude(status__in=["draft"])

    synced_count = 0
    error_count = 0

    for application in applications:
        try:
            sync_loan_application.delay(application.id)
            synced_count += 1
        except Exception as e:
            logger.error(
                f"Error queueing sync for {application.reference_number}: {str(e)}"
            )
            error_count += 1

    if synced_count > 0:
        messages.success(
            request, f"{synced_count} applications queued for synchronization."
        )

    if error_count > 0:
        messages.warning(request, f"{error_count} applications failed to queue.")

    return redirect("loans:application_list")


@login_required
def odoo_sync_status(request):
    """Check Odoo sync status for all applications"""
    applications = LoanApplication.objects.filter(user=request.user)

    sync_info = []
    for application in applications:
        sync_info.append(
            {
                "reference_number": application.reference_number,
                "status": application.status,
                "odoo_application_id": application.odoo_application_id,
                "is_synced": application.odoo_application_id is not None,
                "created_at": application.created_at,
            }
        )

    return JsonResponse(
        {
            "applications": sync_info,
            "total_applications": applications.count(),
            "synced_applications": applications.filter(
                odoo_application_id__isnull=False
            ).count(),
            "pending_sync": applications.filter(odoo_application_id__isnull=True)
            .exclude(status__in=["draft"])
            .count(),
        }
    )


@login_required
def test_odoo_connection(request):
    """Test connection to Odoo"""
    try:
        integration = EnhancedOdooIntegration()
        result = integration.test_connection()

        return JsonResponse(
            {
                "status": "success" if result["status"] == "connected" else "error",
                "result": result,
            }
        )

    except Exception as e:
        return JsonResponse({"status": "error", "error": str(e)})


@login_required
def dashboard_with_sync(request):
    """Enhanced dashboard with sync information"""
    applications = LoanApplication.objects.filter(user=request.user)

    # Sync statistics
    total_applications = applications.count()
    synced_applications = applications.filter(odoo_application_id__isnull=False).count()
    pending_sync = (
        applications.filter(odoo_application_id__isnull=True)
        .exclude(status__in=["draft"])
        .count()
    )

    # Recent applications
    recent_applications = applications.order_by("-created_at")[:5]

    # Status breakdown
    status_breakdown = {}
    for status in LoanApplication.Status:
        status_breakdown[status.value] = applications.filter(
            status=status.value
        ).count()

    context = {
        "total_applications": total_applications,
        "synced_applications": synced_applications,
        "pending_sync": pending_sync,
        "sync_percentage": (synced_applications / total_applications * 100)
        if total_applications > 0
        else 0,
        "recent_applications": recent_applications,
        "status_breakdown": status_breakdown,
    }

    return render(request, "berit/loans/dashboard_with_sync.html", context)
