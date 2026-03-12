# -*- coding: utf-8 -*-
"""
Enhanced Celery tasks for automatic Odoo synchronization
Handles real-time sync of loan applications to Odoo backend
with retry logic, error handling, and status tracking
"""

import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.loans.models import LoanApplication, RepaymentSchedule
from apps.loans.sync.perfect_sync import PerfectOdooSync
from apps.loans.sync.webhook_models import SyncConflict, SyncEvent

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def sync_loan_to_odoo_async(self, application_id):
    """
    Asynchronously sync loan application to Odoo
    Runs as Celery task with automatic retry on failure

    Args:
        application_id: ID of LoanApplication to sync

    Returns:
        dict: Sync result with status and Odoo record ID
    """
    try:
        logger.info(f"Starting async Odoo sync for application {application_id}")

        # Get application
        application = LoanApplication.objects.get(id=application_id)

        # Update sync event status
        sync_event = SyncEvent.objects.filter(
            resource_type="loan_application",
            resource_id=application_id,
            status__in=["pending", "retrying"],
        ).first()

        if sync_event:
            sync_event.status = "processing"
            sync_event.save()

        # Initialize Odoo sync
        sync = PerfectOdooSync()

        # Prepare loan data
        loan_data = {
            "name": application.reference_number,
            "customer_id": application.user.email,
            "loan_amount": float(application.loan_amount),
            "duration_months": application.loan_duration_months,
            "purpose": application.loan_purpose,
            "status": "draft",
            "interest_rate": float(application.interest_rate or 0),
            "monthly_payment": float(application.monthly_repayment or 0),
            "total_repayable": float(application.total_repayable or 0),
            "employment_type": application.employment_type,
            "user_email": application.user.email,
            "user_phone": application.user.phone_number or "",
            "first_name": application.user.first_name,
            "last_name": application.user.last_name,
        }

        # Create or update in Odoo
        result = sync.create_or_update_loan(
            loan_data=loan_data,
            django_record_id=application_id,
            model_name="loan.application",
        )

        if result.get("success"):
            # Update application with Odoo record ID
            odoo_record_id = result.get("odoo_record_id")
            application.odoo_record_id = odoo_record_id
            application.save()

            # Update sync event
            if sync_event:
                sync_event.status = "completed"
                sync_event.odoo_response = result
                sync_event.save()

            logger.info(
                f"Successfully synced application {application_id} to Odoo "
                f"(Odoo ID: {odoo_record_id})"
            )

            # Queue status update task
            update_loan_status_from_odoo.delay(application_id)

            return {
                "success": True,
                "message": "Application synced to Odoo",
                "application_id": application_id,
                "odoo_record_id": odoo_record_id,
            }
        else:
            error_msg = result.get("error", "Unknown error")
            logger.error(f"Failed to sync application {application_id}: {error_msg}")

            # Update sync event with error
            if sync_event:
                sync_event.status = "retrying"
                sync_event.error_message = error_msg
                sync_event.retry_count = (sync_event.retry_count or 0) + 1
                sync_event.save()

            # Retry task with exponential backoff
            raise self.retry(
                exc=Exception(error_msg), countdown=60 * (2**self.request.retries)
            )

    except LoanApplication.DoesNotExist:
        logger.error(f"Application {application_id} not found")
        return {"success": False, "message": "Application not found"}

    except Exception as e:
        logger.error(
            f"Error syncing application {application_id}: {str(e)}", exc_info=True
        )

        # Mark sync event as failed after max retries
        try:
            sync_event = SyncEvent.objects.filter(
                resource_type="loan_application", resource_id=application_id
            ).first()

            if sync_event:
                sync_event.retry_count = (sync_event.retry_count or 0) + 1
                if sync_event.retry_count >= 5:
                    sync_event.status = "failed"
                    sync_event.error_message = str(e)
                else:
                    sync_event.status = "retrying"
                sync_event.save()
        except Exception as update_error:
            logger.error(f"Error updating sync event: {str(update_error)}")

        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (2**self.request.retries))
        else:
            return {
                "success": False,
                "message": f"Max retries exceeded: {str(e)}",
                "application_id": application_id,
            }


@shared_task(bind=True, max_retries=3)
def update_loan_status_from_odoo(self, application_id):
    """
    Poll Odoo for updated loan status and sync back to Django

    Args:
        application_id: ID of LoanApplication

    Returns:
        dict: Status update result
    """
    try:
        logger.info(f"Checking Odoo status for application {application_id}")

        application = LoanApplication.objects.get(id=application_id)

        if not application.odoo_record_id:
            logger.warning(f"No Odoo record ID for application {application_id}")
            return {"success": False, "message": "No Odoo record ID"}

        # Connect to Odoo
        sync = PerfectOdooSync()

        # Fetch loan status from Odoo
        odoo_loan = sync.get_odoo_record(
            model_name="loan.application", record_id=application.odoo_record_id
        )

        if not odoo_loan:
            logger.warning(f"Loan not found in Odoo: {application.odoo_record_id}")
            return {"success": False, "message": "Loan not found in Odoo"}

        # Extract status
        odoo_status = odoo_loan.get("state", "draft")

        # Map Odoo status to Django status
        status_mapping = {
            "draft": "draft",
            "submitted": "submitted",
            "under_review": "under_review",
            "approved": "approved",
            "rejected": "rejected",
            "disbursed": "active",
            "closed": "closed",
        }

        django_status = status_mapping.get(odoo_status, "draft")

        # Update application if status changed
        if application.status != django_status:
            old_status = application.status
            application.status = django_status
            application.last_status_update = timezone.now()
            application.save()

            logger.info(
                f"Updated application {application_id} status from {old_status} to {django_status}"
            )

            # Create sync event for status change
            SyncEvent.objects.create(
                event_type="loan_status_updated",
                direction="odoo_to_django",
                resource_type="loan_application",
                resource_id=application_id,
                status="completed",
                payload={
                    "old_status": old_status,
                    "new_status": django_status,
                    "odoo_status": odoo_status,
                },
            )

            # Send notification email
            notify_user_of_status_change.delay(application_id, django_status)

        return {
            "success": True,
            "application_id": application_id,
            "old_status": application.status,
            "new_status": django_status,
        }

    except LoanApplication.DoesNotExist:
        logger.error(f"Application {application_id} not found")
        return {"success": False, "message": "Application not found"}

    except Exception as e:
        logger.error(f"Error updating status from Odoo: {str(e)}", exc_info=True)

        # Retry
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        else:
            return {"success": False, "message": str(e)}


@shared_task
def periodic_sync_all_applications():
    """
    Periodic task to sync all pending applications to Odoo
    Runs every 30 minutes (configured in CELERY_BEAT_SCHEDULE)
    """
    try:
        logger.info("Starting periodic sync of all pending applications")

        # Get applications in submitted status that haven't been synced
        pending_apps = LoanApplication.objects.filter(
            status="submitted",
            odoo_record_id__isnull=True,
            created_at__gte=timezone.now() - timedelta(days=30),
        )[:100]  # Process up to 100 at a time

        synced_count = 0
        failed_count = 0

        for app in pending_apps:
            try:
                task = sync_loan_to_odoo_async.delay(app.id)
                logger.info(f"Queued sync for application {app.id} (task: {task.id})")
                synced_count += 1
            except Exception as e:
                logger.error(f"Failed to queue sync for application {app.id}: {str(e)}")
                failed_count += 1

        logger.info(
            f"Periodic sync complete: {synced_count} queued, {failed_count} failed"
        )

        return {
            "success": True,
            "queued": synced_count,
            "failed": failed_count,
        }

    except Exception as e:
        logger.error(f"Error in periodic sync task: {str(e)}", exc_info=True)
        return {"success": False, "message": str(e)}


@shared_task
def periodic_status_check():
    """
    Periodic task to check Odoo status for all active loans
    Runs every 15 minutes
    """
    try:
        logger.info("Starting periodic status check from Odoo")

        # Get active applications with Odoo records
        active_apps = LoanApplication.objects.filter(
            status__in=["submitted", "under_review", "approved", "active"],
            odoo_record_id__isnull=False,
        )

        checked_count = 0
        updated_count = 0
        error_count = 0

        for app in active_apps[:50]:  # Check up to 50 at a time
            try:
                result = update_loan_status_from_odoo.delay(app.id)
                checked_count += 1

                if result.get("success"):
                    updated_count += 1

            except Exception as e:
                logger.error(f"Error checking status for app {app.id}: {str(e)}")
                error_count += 1

        logger.info(
            f"Status check complete: {checked_count} checked, "
            f"{updated_count} updated, {error_count} errors"
        )

        return {
            "success": True,
            "checked": checked_count,
            "updated": updated_count,
            "errors": error_count,
        }

    except Exception as e:
        logger.error(f"Error in periodic status check: {str(e)}", exc_info=True)
        return {"success": False, "message": str(e)}


@shared_task
def retry_failed_syncs():
    """
    Retry sync events that have failed
    Runs every hour
    """
    try:
        logger.info("Starting retry of failed sync events")

        # Get failed sync events (max 5 retries)
        failed_events = SyncEvent.objects.filter(
            status__in=["failed", "retrying"],
            retry_count__lt=5,
            resource_type="loan_application",
        ).order_by("created_at")[:20]

        retried_count = 0

        for event in failed_events:
            try:
                # Re-queue sync task
                sync_loan_to_odoo_async.delay(event.resource_id)
                event.status = "retrying"
                event.last_retry_at = timezone.now()
                event.save()

                retried_count += 1
                logger.info(f"Re-queued sync for event {event.id}")

            except Exception as e:
                logger.error(f"Error retrying event {event.id}: {str(e)}")

        logger.info(f"Retry complete: {retried_count} events re-queued")

        return {
            "success": True,
            "retried": retried_count,
        }

    except Exception as e:
        logger.error(f"Error in retry failed syncs: {str(e)}", exc_info=True)
        return {"success": False, "message": str(e)}


@shared_task
def send_application_confirmation_email(application_id, email):
    """
    Send confirmation email after application submission

    Args:
        application_id: ID of LoanApplication
        email: Recipient email address
    """
    try:
        logger.info(f"Sending confirmation email for application {application_id}")

        application = LoanApplication.objects.get(id=application_id)

        context = {
            "application": application,
            "reference_number": application.reference_number,
            "loan_amount": application.loan_amount,
            "application_url": f"{settings.PORTAL_BASE_URL}/loans/applications/{application_id}/",
        }

        # Render email template
        subject = f"Loan Application Received - {application.reference_number}"
        html_message = render_to_string("emails/application_confirmation.html", context)
        plain_message = render_to_string("emails/application_confirmation.txt", context)

        # Send email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(f"Confirmation email sent to {email}")

        return {"success": True, "email": email}

    except LoanApplication.DoesNotExist:
        logger.error(f"Application {application_id} not found")
        return {"success": False, "message": "Application not found"}

    except Exception as e:
        logger.error(f"Error sending confirmation email: {str(e)}", exc_info=True)
        return {"success": False, "message": str(e)}


@shared_task
def notify_user_of_status_change(application_id, new_status):
    """
    Send email notification when loan status changes

    Args:
        application_id: ID of LoanApplication
        new_status: New status value
    """
    try:
        logger.info(
            f"Sending status change notification for application {application_id}"
        )

        application = LoanApplication.objects.get(id=application_id)

        # Status-specific messages
        status_messages = {
            "under_review": "Your application is now under review",
            "approved": "Great news! Your loan has been approved",
            "rejected": "Your application status has been updated",
            "active": "Your loan has been disbursed",
            "closed": "Your loan account has been closed",
        }

        message = status_messages.get(new_status, f"Status changed to {new_status}")

        context = {
            "application": application,
            "reference_number": application.reference_number,
            "new_status": new_status,
            "status_message": message,
            "application_url": f"{settings.PORTAL_BASE_URL}/loans/applications/{application_id}/",
        }

        # Render email
        subject = f"Loan Application Update - {application.reference_number}"
        html_message = render_to_string("emails/status_changed.html", context)
        plain_message = render_to_string("emails/status_changed.txt", context)

        # Send email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[application.user.email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(f"Status change notification sent to {application.user.email}")

        return {"success": True}

    except LoanApplication.DoesNotExist:
        logger.error(f"Application {application_id} not found")
        return {"success": False}

    except Exception as e:
        logger.error(f"Error sending status notification: {str(e)}", exc_info=True)
        return {"success": False, "message": str(e)}


@shared_task
def cleanup_old_sync_events():
    """
    Cleanup old sync events (older than 90 days)
    Runs daily
    """
    try:
        logger.info("Starting cleanup of old sync events")

        cutoff_date = timezone.now() - timedelta(days=90)

        deleted_count, _ = SyncEvent.objects.filter(
            created_at__lt=cutoff_date, status__in=["completed", "failed"]
        ).delete()

        logger.info(f"Cleaned up {deleted_count} old sync events")

        return {
            "success": True,
            "deleted": deleted_count,
        }

    except Exception as e:
        logger.error(f"Error cleaning up sync events: {str(e)}", exc_info=True)
        return {"success": False, "message": str(e)}
