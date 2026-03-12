# -*- coding: utf-8 -*-
"""
Celery tasks for loan management
"""
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from .models import LoanApplication, RepaymentSchedule
from .utils import OdooIntegration


@shared_task
def send_repayment_reminders():
    """Send repayment reminder emails"""
    today = timezone.now().date()
    reminder_date = today + timedelta(days=7)  # 7 days before due date
    
    # Get repayments due in 7 days
    upcoming_repayments = RepaymentSchedule.objects.filter(
        due_date=reminder_date,
        status=RepaymentSchedule.Status.PENDING
    ).select_related('loan_application', 'loan_application__user')
    
    sent_count = 0
    
    for repayment in upcoming_repayments:
        try:
            # Send email reminder
            subject = f"Repayment Reminder - {repayment.loan_application.reference_number}"
            
            context = {
                'user': repayment.loan_application.user,
                'application': repayment.loan_application,
                'repayment': repayment,
                'portal_settings': settings.PORTAL_SETTINGS,
            }
            
            html_message = render_to_string('berit/emails/repayment_reminder.html', context)
            text_message = render_to_string('berit/emails/repayment_reminder.txt', context)
            
            send_mail(
                subject=subject,
                message=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[repayment.loan_application.user.email],
                html_message=html_message,
                fail_silently=False
            )
            
            sent_count += 1
            
        except Exception as e:
            # Log error but continue with other reminders
            print(f"Error sending repayment reminder to {repayment.loan_application.user.email}: {str(e)}")
    
    return f"Sent {sent_count} repayment reminders"


@shared_task
def sync_loan_statuses():
    """Sync loan statuses from Odoo"""
    try:
        odoo_integration = OdooIntegration()
        updated_count = 0
        
        # Get all applications with Odoo IDs
        applications = LoanApplication.objects.filter(
            odoo_application_id__isnull=False
        )
        
        for application in applications:
            try:
                # Get status from Odoo
                odoo_data = odoo_integration.get_loan_status(application.odoo_application_id)
                
                if odoo_data:
                    odoo_status = odoo_data.get('state')
                    
                    # Map Odoo status to Django status
                    status_mapping = {
                        'draft': LoanApplication.Status.DRAFT,
                        'submitted': LoanApplication.Status.SUBMITTED,
                        'under_review': LoanApplication.Status.UNDER_REVIEW,
                        'approved': LoanApplication.Status.APPROVED,
                        'rejected': LoanApplication.Status.REJECTED,
                        'disbursed': LoanApplication.Status.DISBURSED,
                        'active': LoanApplication.Status.ACTIVE,
                        'closed': LoanApplication.Status.CLOSED,
                        'defaulted': LoanApplication.Status.DEFAULTED,
                    }
                    
                    django_status = status_mapping.get(odoo_status)
                    
                    if django_status and application.status != django_status:
                        # Update status
                        old_status = application.status
                        application.status = django_status
                        
                        # Update dates based on status
                        if django_status == LoanApplication.Status.APPROVED:
                            application.approved_at = timezone.now()
                        elif django_status == LoanApplication.Status.DISBURSED:
                            application.disbursed_at = timezone.now()
                        
                        application.save()
                        updated_count += 1
                        
                        # Send status change notification
                        send_status_change_notification.delay(
                            application.id, old_status, django_status
                        )
                        
            except Exception as e:
                print(f"Error syncing application {application.reference_number}: {str(e)}")
                continue
        
        return f"Synced {updated_count} loan applications"
        
    except Exception as e:
        return f"Error syncing loan statuses: {str(e)}"


@shared_task
def send_status_change_notification(application_id, old_status, new_status):
    """Send status change notification to user"""
    try:
        application = LoanApplication.objects.get(id=application_id)
        
        # Don't send notifications for draft status changes
        if new_status == LoanApplication.Status.DRAFT:
            return
        
        subject = f"Loan Application Status Update - {application.reference_number}"
        
        context = {
            'user': application.user,
            'application': application,
            'old_status': old_status,
            'new_status': new_status,
            'portal_settings': settings.PORTAL_SETTINGS,
        }
        
        html_message = render_to_string('berit/emails/status_update.html', context)
        text_message = render_to_string('berit/emails/status_update.txt', context)
        
        send_mail(
            subject=subject,
            message=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[application.user.email],
            html_message=html_message,
            fail_silently=False
        )
        
        return f"Sent status notification to {application.user.email}"
        
    except Exception as e:
        return f"Error sending status notification: {str(e)}"


@shared_task
def send_welcome_email(user_id):
    """Send welcome email to new user"""
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        user = User.objects.get(id=user_id)
        
        subject = "Welcome to Berit Shalvah Financial Services"
        
        context = {
            'user': user,
            'portal_settings': settings.PORTAL_SETTINGS,
        }
        
        html_message = render_to_string('berit/emails/welcome.html', context)
        text_message = render_to_string('berit/emails/welcome.txt', context)
        
        send_mail(
            subject=subject,
            message=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False
        )
        
        return f"Sent welcome email to {user.email}"
        
    except Exception as e:
        return f"Error sending welcome email: {str(e)}"


@shared_task
def send_application_confirmation(application_id):
    """Send application confirmation email"""
    try:
        application = LoanApplication.objects.get(id=application_id)
        
        subject = f"Loan Application Received - {application.reference_number}"
        
        context = {
            'user': application.user,
            'application': application,
            'portal_settings': settings.PORTAL_SETTINGS,
        }
        
        html_message = render_to_string('berit/emails/application_confirmation.html', context)
        text_message = render_to_string('berit/emails/application_confirmation.txt', context)
        
        send_mail(
            subject=subject,
            message=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[application.user.email],
            html_message=html_message,
            fail_silently=False
        )
        
        return f"Sent application confirmation to {application.user.email}"
        
    except Exception as e:
        return f"Error sending application confirmation: {str(e)}"


@shared_task
def generate_loan_agreement_pdf(application_id):
    """Generate loan agreement PDF and send to user"""
    try:
        application = LoanApplication.objects.get(id=application_id)
        
        if application.status != LoanApplication.Status.APPROVED:
            return f"Application {application.reference_number} is not approved"
        
        # Generate PDF using WeasyPrint
        from weasyprint import HTML, CSS
        
        html_content = render_to_string('berit/loans/loan_agreement_pdf.html', {
            'application': application,
            'portal_settings': settings.PORTAL_SETTINGS,
        })
        
        css = CSS(string='''
            @page {
                size: A4;
                margin: 2cm;
            }
            body {
                font-family: Arial, sans-serif;
                font-size: 12px;
                line-height: 1.4;
            }
        ''')
        
        pdf = HTML(string=html_content).write_pdf(stylesheets=[css])
        
        # Save PDF to media storage
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile
        
        filename = f"loan_agreements/{application.reference_number}.pdf"
        path = default_storage.save(filename, ContentFile(pdf))
        
        # Update application with PDF path
        # (You might want to add a pdf_file field to the model)
        
        # Send email with PDF attachment
        subject = f"Loan Agreement - {application.reference_number}"
        
        context = {
            'user': application.user,
            'application': application,
            'portal_settings': settings.PORTAL_SETTINGS,
        }
        
        html_message = render_to_string('berit/emails/loan_agreement.html', context)
        text_message = render_to_string('berit/emails/loan_agreement.txt', context)
        
        send_mail(
            subject=subject,
            message=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[application.user.email],
            html_message=html_message,
            fail_silently=False
        )
        
        return f"Generated and sent loan agreement for {application.reference_number}"
        
    except Exception as e:
        return f"Error generating loan agreement: {str(e)}"


@shared_task
def cleanup_old_draft_applications():
    """Clean up draft applications older than 30 days"""
    cutoff_date = timezone.now() - timedelta(days=30)
    
    old_drafts = LoanApplication.objects.filter(
        status=LoanApplication.Status.DRAFT,
        created_at__lt=cutoff_date
    )
    
    deleted_count = old_drafts.count()
    old_drafts.delete()
    
    return f"Deleted {deleted_count} old draft applications"


@shared_task
def update_overdue_repayments():
    """Mark overdue repayments and calculate penalties"""
    today = timezone.now().date()
    
    # Get pending repayments that are overdue
    overdue_repayments = RepaymentSchedule.objects.filter(
        due_date__lt=today,
        status=RepaymentSchedule.Status.PENDING
    )
    
    updated_count = 0
    
    for repayment in overdue_repayments:
        # Calculate days overdue
        days_overdue = (today - repayment.due_date).days
        repayment.days_overdue = days_overdue
        
        # Calculate penalty (1% per day)
        penalty_rate = Decimal('0.01')
        repayment.penalty_amount = repayment.total_due * (penalty_rate * days_overdue)
        
        # Update status
        repayment.status = RepaymentSchedule.Status.OVERDUE
        repayment.save()
        
        updated_count += 1
        
        # Check if loan should be marked as defaulted
        if days_overdue > 30:
            application = repayment.loan_application
            if application.status == LoanApplication.Status.ACTIVE:
                application.status = LoanApplication.Status.DEFAULTED
                application.save()
                
                # Send default notification
                send_default_notification.delay(application.id)
    
    return f"Updated {updated_count} overdue repayments"


@shared_task
def send_default_notification(application_id):
    """Send loan default notification"""
    try:
        application = LoanApplication.objects.get(id=application_id)
        
        subject = f"Urgent: Loan Default Notice - {application.reference_number}"
        
        context = {
            'user': application.user,
            'application': application,
            'portal_settings': settings.PORTAL_SETTINGS,
        }
        
        html_message = render_to_string('berit/emails/default_notice.html', context)
        text_message = render_to_string('berit/emails/default_notice.txt', context)
        
        send_mail(
            subject=subject,
            message=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[application.user.email],
            html_message=html_message,
            fail_silently=False
        )
        
        return f"Sent default notification to {application.user.email}"
        
    except Exception as e:
        return f"Error sending default notification: {str(e)}"
