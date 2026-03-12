# -*- coding: utf-8 -*-
"""
Enhanced Celery tasks for complete Django-Odoo synchronization
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import LoanApplication, RepaymentSchedule
from .odoo_sync import EnhancedOdooIntegration

logger = logging.getLogger(__name__)


@shared_task
def complete_sync_all_loans():
    """Complete synchronization of all loans between Django and Odoo"""
    try:
        integration = EnhancedOdooIntegration()
        result = integration.sync_all_loans()

        logger.info(f"Complete sync result: {result}")
        return result

    except Exception as e:
        logger.error(f"Complete sync error: {str(e)}")
        return {"error": str(e)}


@shared_task
def sync_loan_application(application_id):
    """Sync a single loan application to Odoo"""
    try:
        application = LoanApplication.objects.get(id=application_id)
        integration = EnhancedOdooIntegration()

        if not application.odoo_application_id:
            odoo_id = integration.create_loan_application(application)
            application.odoo_application_id = odoo_id
            application.save()

            logger.info(
                f"Synced application {application.reference_number} to Odoo (ID: {odoo_id})"
            )
            return {"status": "success", "odoo_id": odoo_id}
        else:
            # Update existing application
            integration.update_loan_status(
                application.odoo_application_id,
                integration._map_django_status_to_odoo(application.status),
            )

            logger.info(f"Updated application {application.reference_number} in Odoo")
            return {"status": "updated", "odoo_id": application.odoo_application_id}

    except Exception as e:
        logger.error(f"Error syncing application {application_id}: {str(e)}")
        return {"error": str(e)}


@shared_task
def sync_loan_statuses_from_odoo():
    """Sync loan statuses from Odoo to Django"""
    try:
        integration = EnhancedOdooIntegration()
        updated_count = 0

        # Get all applications with Odoo IDs
        applications = LoanApplication.objects.filter(odoo_application_id__isnull=False)

        for application in applications:
            try:
                # Get status from Odoo
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
                        updated_count += 1

                        logger.info(
                            f"Updated {application.reference_number}: {old_status} → {django_status}"
                        )

                        # Send status change notification
                        send_status_change_notification.delay(
                            application.id, old_status, django_status
                        )

            except Exception as e:
                logger.error(
                    f"Error syncing application {application.reference_number}: {str(e)}"
                )
                continue

        logger.info(f"Synced {updated_count} loan applications from Odoo")
        return f"Synced {updated_count} loan applications from Odoo"

    except Exception as e:
        logger.error(f"Error syncing loan statuses from Odoo: {str(e)}")
        return f"Error syncing loan statuses: {str(e)}"


@shared_task
def sync_repayment_schedules():
    """Sync repayment schedules between Django and Odoo"""
    try:
        integration = EnhancedOdooIntegration()
        sync_count = 0

        # Get approved/disbursed loans without repayment schedules
        applications = LoanApplication.objects.filter(
            status__in=["approved", "disbursed", "active"],
            repayment_schedule__isnull=True,
            odoo_application_id__isnull=False,
        )

        for application in applications:
            try:
                # Create repayment schedule in Django if not exists
                if application.repayment_schedule.count() == 0:
                    from .utils import LoanCalculator

                    calculator = LoanCalculator()

                    schedule = calculator.generate_amortization_schedule(
                        application.loan_amount,
                        application.interest_rate,
                        application.loan_duration,
                        application.disbursed_at.date()
                        if application.disbursed_at
                        else None,
                    )

                    for installment in schedule:
                        RepaymentSchedule.objects.create(
                            loan_application=application,
                            installment_number=installment["installment_number"],
                            due_date=installment["due_date"],
                            principal_amount=installment["principal_amount"],
                            interest_amount=installment["interest_amount"],
                            total_due=installment["total_due"],
                            status=RepaymentSchedule.Status.PENDING,
                        )

                    sync_count += 1
                    logger.info(
                        f"Created repayment schedule for {application.reference_number}"
                    )

            except Exception as e:
                logger.error(
                    f"Error creating repayment schedule for {application.reference_number}: {str(e)}"
                )
                continue

        logger.info(f"Created {sync_count} repayment schedules")
        return f"Created {sync_count} repayment schedules"

    except Exception as e:
        logger.error(f"Error syncing repayment schedules: {str(e)}")
        return f"Error syncing repayment schedules: {str(e)}"


@shared_task
def auto_sync_new_applications():
    """Automatically sync new applications to Odoo"""
    try:
        # Get applications submitted in the last hour that haven't been synced
        one_hour_ago = timezone.now() - timedelta(hours=1)

        applications = LoanApplication.objects.filter(
            created_at__gte=one_hour_ago,
            odoo_application_id__isnull=True,
            status__in=["submitted", "under_review", "approved", "disbursed", "active"],
        )

        sync_count = 0
        for application in applications:
            try:
                sync_loan_application.delay(application.id)
                sync_count += 1
            except Exception as e:
                logger.error(
                    f"Error queueing sync for {application.reference_number}: {str(e)}"
                )

        logger.info(f"Queued {sync_count} new applications for sync")
        return f"Queued {sync_count} new applications for sync"

    except Exception as e:
        logger.error(f"Error auto-syncing new applications: {str(e)}")
        return f"Error auto-syncing new applications: {str(e)}"


@shared_task
def test_odoo_connection():
    """Test connection to Odoo"""
    try:
        integration = EnhancedOdooIntegration()
        result = integration.test_connection()

        if result["status"] == "connected":
            logger.info("Odoo connection test successful")
            return "Odoo connection test successful"
        else:
            logger.error(f"Odoo connection test failed: {result['error']}")
            return f"Odoo connection test failed: {result['error']}"

    except Exception as e:
        logger.error(f"Odoo connection test error: {str(e)}")
        return f"Odoo connection test error: {str(e)}"


@shared_task
def send_status_change_notification(application_id, old_status, new_status):
    """Send status change notification to user"""
    try:
        application = LoanApplication.objects.get(id=application_id)

        # Don't send notifications for draft status changes
        if new_status == LoanApplication.Status.DRAFT:
            return

        from django.core.mail import send_mail
        from django.template.loader import render_to_string

        subject = f"Loan Application Status Update - {application.reference_number}"

        context = {
            "user": application.user,
            "application": application,
            "old_status": old_status,
            "new_status": new_status,
            "portal_settings": getattr(settings, "PORTAL_SETTINGS", {}),
        }

        html_message = render_to_string("berit/emails/status_update.html", context)
        text_message = render_to_string("berit/emails/status_update.txt", context)

        send_mail(
            subject=subject,
            message=text_message,
            from_email=getattr(
                settings, "DEFAULT_FROM_EMAIL", "noreply@beritshalvah.com"
            ),
            recipient_list=[application.user.email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(f"Sent status notification to {application.user.email}")
        return f"Sent status notification to {application.user.email}"

    except Exception as e:
        logger.error(f"Error sending status notification: {str(e)}")
        return f"Error sending status notification: {str(e)}"


# Periodic sync tasks
@shared_task
def periodic_sync_all():
    """Periodic complete sync (runs every 30 minutes)"""
    return complete_sync_all_loans()


@shared_task
def periodic_status_sync():
    """Periodic status sync (runs every 15 minutes)"""
    return sync_loan_statuses_from_odoo()


@shared_task
def periodic_repayment_sync():
    """Periodic repayment sync (runs every hour)"""
    return sync_repayment_schedules()


# ── Tasks imported by modern_wizard_views ─────────────────────────────────────


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_loan_to_odoo_async(self, application_id):
    """
    Async task: push a single loan application to Odoo immediately after
    submission.  Retries up to 3 times on transient errors.
    """
    try:
        application = LoanApplication.objects.get(id=application_id)

        # Try to import the PerfectOdooSync first; fall back to the legacy
        # EnhancedOdooIntegration if the sync module isn't available.
        try:
            from .sync.perfect_sync import PerfectOdooSync

            sync = PerfectOdooSync()
            result = sync.sync_loan_to_odoo(application)
            logger.info(
                f"[sync_loan_to_odoo_async] PerfectOdooSync result for "
                f"{application.reference_number}: {result}"
            )
            return result
        except Exception as sync_err:
            logger.warning(
                f"[sync_loan_to_odoo_async] PerfectOdooSync unavailable "
                f"({sync_err}); falling back to EnhancedOdooIntegration"
            )

        # Fallback: legacy integration
        integration = EnhancedOdooIntegration()
        if not application.odoo_application_id:
            odoo_id = integration.create_loan_application(application)
            application.odoo_application_id = odoo_id
            application.save(update_fields=["odoo_application_id"])
            logger.info(
                f"[sync_loan_to_odoo_async] Created Odoo record {odoo_id} "
                f"for {application.reference_number}"
            )
            return {"status": "created", "odoo_id": odoo_id}
        else:
            integration.update_loan_status(
                application.odoo_application_id,
                integration._map_django_status_to_odoo(application.status),
            )
            logger.info(
                f"[sync_loan_to_odoo_async] Updated Odoo record "
                f"{application.odoo_application_id} for {application.reference_number}"
            )
            return {
                "status": "updated",
                "odoo_id": application.odoo_application_id,
            }

    except LoanApplication.DoesNotExist:
        logger.error(
            f"[sync_loan_to_odoo_async] Application {application_id} not found"
        )
        return {"error": "Application not found"}
    except Exception as exc:
        logger.error(
            f"[sync_loan_to_odoo_async] Error syncing {application_id}: {exc}",
            exc_info=True,
        )
        # Retry with exponential back-off
        raise self.retry(exc=exc)


@shared_task
def send_application_confirmation_email(application_id, email):
    """
    Send a confirmation e-mail to the applicant after successful submission.
    Errors are logged but never bubble up to avoid breaking the submission
    response.
    """
    try:
        application = LoanApplication.objects.get(id=application_id)

        from django.core.mail import send_mail
        from django.template.loader import render_to_string

        context = {
            "application": application,
            "user": application.user,
            "portal_settings": getattr(settings, "PORTAL_SETTINGS", {}),
        }

        # Try HTML template; fall back to plain text if template is missing.
        try:
            html_message = render_to_string(
                "emails/application_confirmation.html", context
            )
        except Exception:
            html_message = None

        plain_message = (
            f"Dear {application.user.get_full_name() or application.user.email},\n\n"
            f"Thank you for submitting your loan application.\n\n"
            f"Reference Number : {application.reference_number}\n"
            f"Amount Requested : KES {application.loan_amount:,.2f}\n"
            f"Duration         : {application.loan_duration} months\n\n"
            f"Our team will review your application and get back to you shortly.\n\n"
            f"Regards,\nBerit Shalvah Financial Services"
        )

        send_mail(
            subject=f"Loan Application Received – {application.reference_number}",
            message=plain_message,
            from_email=getattr(
                settings, "DEFAULT_FROM_EMAIL", "noreply@beritshalvah.co.ke"
            ),
            recipient_list=[email],
            html_message=html_message,
            fail_silently=True,
        )

        logger.info(
            f"[send_application_confirmation_email] Sent confirmation to {email} "
            f"for {application.reference_number}"
        )
        return f"Confirmation sent to {email}"

    except LoanApplication.DoesNotExist:
        logger.error(
            f"[send_application_confirmation_email] Application {application_id} not found"
        )
    except Exception as exc:
        logger.error(
            f"[send_application_confirmation_email] Failed to send to {email}: {exc}",
            exc_info=True,
        )
