# -*- coding: utf-8 -*-
"""
Webhook views for receiving real-time events from Odoo
"""
import json
import hashlib
import hmac
import logging
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
from django.utils import timezone

from .webhook_models import SyncEvent, WebhookSubscription, SyncLock
from .enhanced_sync import RobustOdooSync
from apps.loans.models import LoanApplication, RepaymentSchedule

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class OdooWebhookView(View):
    """
    Webhook endpoint to receive real-time events from Odoo
    """
    
    def post(self, request, *args, **kwargs):
        """Handle incoming webhook from Odoo"""
        try:
            # Parse the payload
            try:
                payload = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({'error': 'Invalid JSON'}, status=400)
            
            # Get webhook signature
            signature = request.headers.get('X-Odoo-Signature', '')
            
            # Get event type
            event_type = payload.get('event_type', '')
            
            # Log incoming webhook
            logger.info(f"Received webhook: {event_type}")
            
            # Create sync event record
            sync_event = SyncEvent.objects.create(
                event_type=event_type,
                direction=SyncEvent.Direction.ODOO_TO_DJANGO,
                status=SyncEvent.Status.PENDING,
                payload=payload,
                webhook_signature=signature,
                odoo_record_id=payload.get('record_id'),
                source_timestamp=timezone.now()
            )
            
            # Verify signature if we have a subscription
            webhook_url = getattr(settings, 'ODOO_WEBHOOK_URL', '')
            if webhook_url:
                subscription = WebhookSubscription.objects.filter(
                    event=event_type,
                    is_active=True
                ).first()
                
                if subscription:
                    payload_str = json.dumps(payload, sort_keys=True)
                    sync_event.signature_verified = subscription.verify_signature(
                        payload_str, signature
                    )
                    sync_event.save()
            
            # Process the event
            result = self._process_event(sync_event, payload)
            
            if result['success']:
                sync_event.mark_completed(response_data=result)
                return JsonResponse({
                    'status': 'success',
                    'event_id': str(sync_event.id),
                    'message': result.get('message', 'Event processed')
                })
            else:
                sync_event.mark_failed(result.get('error', 'Unknown error'))
                return JsonResponse({
                    'status': 'error',
                    'event_id': str(sync_event.id),
                    'error': result.get('error', 'Unknown error')
                }, status=500)
                
        except Exception as e:
            logger.exception(f"Error processing webhook: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'error': str(e)
            }, status=500)
    
    def _process_event(self, sync_event, payload):
        """Process the webhook event"""
        event_type = payload.get('event_type')
        record_id = payload.get('record_id')
        data = payload.get('data', {})
        
        # Acquire lock for this resource
        lock_acquired = SyncLock.acquire(
            SyncLock.LockType.LOAN_APPLICATION,
            str(record_id),
            f'webhook_{event_type}'
        )
        
        if not lock_acquired:
            return {
                'success': False,
                'error': 'Resource is currently being processed'
            }
        
        try:
            if event_type in ['loan.created', 'loan.updated', 'loan.status.changed']:
                return self._handle_loan_event(payload)
            elif event_type == 'loan.approved':
                return self._handle_loan_approved(payload)
            elif event_type == 'loan.rejected':
                return self._handle_loan_rejected(payload)
            elif event_type == 'loan.disbursed':
                return self._handle_loan_disbursed(payload)
            elif event_type == 'repayment.recorded':
                return self._handle_repayment_recorded(payload)
            else:
                return {
                    'success': True,
                    'message': f'Unknown event type: {event_type}'
                }
        finally:
            # Release lock
            SyncLock.objects.filter(
                lock_type=SyncLock.LockType.LOAN_APPLICATION,
                resource_id=str(record_id)
            ).update(is_released=True)
    
    def _handle_loan_event(self, payload):
        """Handle general loan events"""
        data = payload.get('data', {})
        portal_ref = data.get('portal_application_ref')
        
        if not portal_ref:
            return {'success': False, 'error': 'No portal reference'}
        
        try:
            application = LoanApplication.objects.get(reference_number=portal_ref)
            
            # Update from Odoo data
            if 'state' in data:
                application.status = self._map_odoo_status(data['state'])
            if 'loan_amount' in data:
                application.loan_amount = data['loan_amount']
            if 'loan_duration' in data:
                application.loan_duration = data['loan_duration']
            if 'interest_rate' in data:
                application.interest_rate = data['interest_rate']
            if 'monthly_repayment' in data:
                application.monthly_repayment = data['monthly_repayment']
            if 'total_repayable' in data:
                application.total_repayable = data['total_repayable']
            if 'kyc_verified' in data:
                application.kyc_verified = data['kyc_verified']
            if 'crb_cleared' in data:
                application.crb_cleared = data['crb_cleared']
            if 'notes' in data:
                application.notes = data['notes']
            
            application.save()
            
            return {
                'success': True,
                'message': f'Updated loan {portal_ref}'
            }
        except LoanApplication.DoesNotExist:
            return {'success': False, 'error': 'Loan not found'}
    
    def _handle_loan_approved(self, payload):
        """Handle loan approved event"""
        data = payload.get('data', {})
        portal_ref = data.get('portal_application_ref')
        
        if not portal_ref:
            return {'success': False, 'error': 'No portal reference'}
        
        try:
            application = LoanApplication.objects.get(reference_number=portal_ref)
            application.status = LoanApplication.Status.APPROVED
            application.approved_at = timezone.now()
            application.save()
            
            # Generate repayment schedule
            self._generate_repayment_schedule(application)
            
            return {
                'success': True,
                'message': f'Loan {portal_ref} approved'
            }
        except LoanApplication.DoesNotExist:
            return {'success': False, 'error': 'Loan not found'}
    
    def _handle_loan_rejected(self, payload):
        """Handle loan rejected event"""
        data = payload.get('data', {})
        portal_ref = data.get('portal_application_ref')
        
        if not portal_ref:
            return {'success': False, 'error': 'No portal reference'}
        
        try:
            application = LoanApplication.objects.get(reference_number=portal_ref)
            application.status = LoanApplication.Status.REJECTED
            application.rejection_reason = data.get('rejection_reason', 'Not specified')
            application.save()
            
            return {
                'success': True,
                'message': f'Loan {portal_ref} rejected'
            }
        except LoanApplication.DoesNotExist:
            return {'success': False, 'error': 'Loan not found'}
    
    def _handle_loan_disbursed(self, payload):
        """Handle loan disbursed event"""
        data = payload.get('data', {})
        portal_ref = data.get('portal_application_ref')
        
        if not portal_ref:
            return {'success': False, 'error': 'No portal reference'}
        
        try:
            application = LoanApplication.objects.get(reference_number=portal_ref)
            application.status = LoanApplication.Status.DISBURSED
            application.disbursed_at = timezone.now()
            application.save()
            
            # Regenerate repayment schedule with actual disbursement date
            application.repayment_schedule.all().delete()
            self._generate_repayment_schedule(application)
            
            return {
                'success': True,
                'message': f'Loan {portal_ref} disbursed'
            }
        except LoanApplication.DoesNotExist:
            return {'success': False, 'error': 'Loan not found'}
    
    def _handle_repayment_recorded(self, payload):
        """Handle repayment recorded event"""
        data = payload.get('data', {})
        portal_ref = data.get('portal_application_ref')
        installment_number = data.get('installment_number')
        
        if not portal_ref or not installment_number:
            return {'success': False, 'error': 'Missing required fields'}
        
        try:
            application = LoanApplication.objects.get(reference_number=portal_ref)
            
            repayment = application.repayment_schedule.filter(
                installment_number=installment_number
            ).first()
            
            if repayment:
                repayment.status = RepaymentSchedule.Status.PAID
                repayment.amount_paid = data.get('amount_paid', repayment.total_due)
                repayment.payment_date = timezone.now().date()
                repayment.payment_method = data.get('payment_method', 'other')
                repayment.payment_reference = data.get('payment_reference', '')
                repayment.save()
            
            return {
                'success': True,
                'message': f'Repayment recorded for {portal_ref}'
            }
        except LoanApplication.DoesNotExist:
            return {'success': False, 'error': 'Loan not found'}
    
    def _generate_repayment_schedule(self, application):
        """Generate repayment schedule for a loan"""
        from apps.loans.utils import LoanCalculator
        
        calculator = LoanCalculator()
        
        schedule = calculator.generate_amortization_schedule(
            application.loan_amount,
            application.interest_rate,
            application.loan_duration,
            application.disbursed_at.date() if application.disbursed_at else None
        )
        
        for installment in schedule:
            RepaymentSchedule.objects.create(
                loan_application=application,
                installment_number=installment['installment_number'],
                due_date=installment['due_date'],
                principal_amount=installment['principal_amount'],
                interest_amount=installment['interest_amount'],
                total_due=installment['total_due'],
                status=RepaymentSchedule.Status.PENDING
            )
    
    def _map_odoo_status(self, odoo_status):
        """Map Odoo status to Django status"""
        mapping = {
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
        return mapping.get(odoo_status, LoanApplication.Status.DRAFT)


# Webhook endpoint instance
odoo_webhook = OdooWebhookView.as_view()


def register_webhook(request):
    """
    API endpoint to register a webhook subscription
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    event = data.get('event')
    webhook_url = data.get('webhook_url')
    
    if not event or not webhook_url:
        return JsonResponse({'error': 'Missing required fields'}, status=400)
    
    # Create or update subscription
    subscription, created = WebhookSubscription.objects.update_or_create(
        event=event,
        webhook_url=webhook_url,
        defaults={
            'is_active': True,
            'custom_headers': data.get('headers', {})
        }
    )
    
    return JsonResponse({
        'status': 'success',
        'subscription_id': str(subscription.id),
        'secret_key': subscription.secret_key,
        'message': 'Webhook registered successfully'
    })


def unregister_webhook(request):
    """
    API endpoint to unregister a webhook subscription
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    event = data.get('event')
    webhook_url = data.get('webhook_url')
    
    if not event or not webhook_url:
        return JsonResponse({'error': 'Missing required fields'}, status=400)
    
    deleted, _ = WebhookSubscription.objects.filter(
        event=event,
        webhook_url=webhook_url
    ).delete()
    
    if deleted:
        return JsonResponse({'status': 'success', 'message': 'Webhook unregistered'})
    else:
        return JsonResponse({'error': 'Webhook not found'}, status=404)


def webhook_status(request):
    """
    Get webhook delivery status
    """
    event_id = request.GET.get('event_id')
    
    if not event_id:
        return JsonResponse({'error': 'Missing event_id'}, status=400)
    
    try:
        event = SyncEvent.objects.get(id=event_id)
        return JsonResponse({
            'event_id': str(event.id),
            'event_type': event.event_type,
            'status': event.status,
            'created_at': event.created_at.isoformat(),
            'completed_at': event.completed_at.isoformat() if event.completed_at else None,
            'error_message': event.error_message,
            'duration': event.duration
        })
    except SyncEvent.DoesNotExist:
        return JsonResponse({'error': 'Event not found'}, status=404)
