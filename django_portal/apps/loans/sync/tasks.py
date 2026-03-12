# -*- coding: utf-8 -*-
"""
Celery tasks for robust synchronization
"""
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

from .enhanced_sync import RobustOdooSync
from .webhook_models import SyncEvent, SyncLock, SyncConflict

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def robust_sync_loan_to_odoo(self, application_id):
    """
    Robust task to sync a loan to Odoo with retry logic
    """
    from apps.loans.models import LoanApplication
    
    try:
        application = LoanApplication.objects.get(id=application_id)
        sync = RobustOdooSync()
        result = sync.sync_loan_to_odoo(application)
        
        if result['success']:
            logger.info(f"Successfully synced loan {application.reference_number} to Odoo")
            return result
        else:
            # Retry if failed
            if self.request.retries < self.max_retries:
                raise self.retry(
                    exc=Exception(result.get('error', 'Sync failed')),
                    countdown=60 * (2 ** self.request.retries)
                )
            return result
            
    except LoanApplication.DoesNotExist:
        logger.error(f"Loan application {application_id} not found")
        return {'success': False, 'error': 'Loan not found'}
    except Exception as e:
        logger.exception(f"Error syncing loan to Odoo: {str(e)}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        return {'success': False, 'error': str(e)}


@shared_task(bind=True, max_retries=3)
def robust_sync_loan_from_odoo(self, application_id):
    """
    Robust task to sync a loan from Odoo with retry logic
    """
    from apps.loans.models import LoanApplication
    
    try:
        application = LoanApplication.objects.get(id=application_id)
        sync = RobustOdooSync()
        result = sync.sync_loan_from_odoo(application)
        
        if result.get('conflict'):
            logger.warning(f"Conflict detected for loan {application.reference_number}")
            # Don't retry conflicts
            return result
        
        if result['success']:
            logger.info(f"Successfully synced loan {application.reference_number} from Odoo")
            return result
        else:
            if self.request.retries < self.max_retries:
                raise self.retry(
                    exc=Exception(result.get('error', 'Sync failed')),
                    countdown=60 * (2 ** self.request.retries)
                )
            return result
            
    except LoanApplication.DoesNotExist:
        logger.error(f"Loan application {application_id} not found")
        return {'success': False, 'error': 'Loan not found'}
    except Exception as e:
        logger.exception(f"Error syncing loan from Odoo: {str(e)}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        return {'success': False, 'error': str(e)}


@shared_task
def process_pending_sync_events():
    """
    Process pending sync events that failed or need retry
    """
    # Get pending events
    pending_events = SyncEvent.objects.filter(
        status__in=[SyncEvent.Status.PENDING, SyncEvent.Status.RETRY]
    ).order_by('created_at')[:50]
    
    processed = 0
    for event in pending_events:
        try:
            # Check if ready to process (not waiting for retry)
            if event.status == SyncEvent.Status.RETRY and event.next_retry_at:
                if timezone.now() < event.next_retry_at:
                    continue
            
            event.mark_started()
            
            # Process based on direction
            if event.direction == SyncEvent.Direction.DJANGO_TO_ODOO:
                _process_django_to_odoo_event(event)
            elif event.direction == SyncEvent.Direction.ODOO_TO_DJANGO:
                _process_odoo_to_django_event(event)
            
            processed += 1
            
        except Exception as e:
            logger.exception(f"Error processing sync event {event.id}: {str(e)}")
            event.mark_failed(str(e))
    
    logger.info(f"Processed {processed} sync events")
    return f"Processed {processed} events"


def _process_django_to_odoo_event(event):
    """Process a Django to Odoo sync event"""
    from apps.loans.models import LoanApplication
    
    if not event.loan_application_id:
        event.mark_failed("No loan application ID")
        return
    
    try:
        application = LoanApplication.objects.get(id=event.loan_application_id)
        sync = RobustOdooSync()
        result = sync.sync_loan_to_odoo(application, create_event=False)
        
        if result['success']:
            event.mark_completed(result)
        else:
            if event.should_retry():
                event.schedule_retry()
            else:
                event.mark_failed(result.get('error', 'Sync failed'))
                
    except LoanApplication.DoesNotExist:
        event.mark_failed("Loan application not found")


def _process_odoo_to_django_event(event):
    """Process an Odoo to Django sync event"""
    from apps.loans.models import LoanApplication
    
    if not event.loan_application_id:
        event.mark_failed("No loan application ID")
        return
    
    try:
        application = LoanApplication.objects.get(id=event.loan_application_id)
        sync = RobustOdooSync()
        result = sync.sync_loan_from_odoo(application)
        
        if result.get('conflict'):
            # Don't mark as failed, just log
            event.mark_completed({'message': 'Conflict detected'})
        elif result['success']:
            event.mark_completed(result)
        else:
            if event.should_retry():
                event.schedule_retry()
            else:
                event.mark_failed(result.get('error', 'Sync failed'))
                
    except LoanApplication.DoesNotExist:
        event.mark_failed("Loan application not found")


@shared_task
def resolve_sync_conflicts():
    """
    Automatically resolve pending sync conflicts
    """
    pending_conflicts = SyncConflict.objects.filter(
        resolution=SyncConflict.Resolution.PENDING
    )
    
    resolved = 0
    for conflict in pending_conflicts:
        try:
            conflict.auto_resolve()
            resolved += 1
            
            # Apply the resolution
            if conflict.resolution == SyncConflict.Resolution.USE_DJANGO:
                # Sync Django version to Odoo
                _apply_django_version_to_odoo(conflict)
            elif conflict.resolution == SyncConflict.Resolution.USE_ODOO:
                # Sync Odoo version to Django
                _apply_odoo_version_to_django(conflict)
                
        except Exception as e:
            logger.exception(f"Error resolving conflict {conflict.id}: {str(e)}")
    
    logger.info(f"Resolved {resolved} sync conflicts")
    return f"Resolved {resolved} conflicts"


def _apply_django_version_to_odoo(conflict):
    """Apply Django version to Odoo"""
    from apps.loans.models import LoanApplication
    
    try:
        application = LoanApplication.objects.get(id=conflict.resource_id)
        sync = RobustOdooSync()
        sync.sync_loan_to_odoo(application)
    except Exception as e:
        logger.error(f"Error applying Django version to Odoo: {str(e)}")


def _apply_odoo_version_to_django(conflict):
    """Apply Odoo version to Django"""
    from apps.loans.models import LoanApplication
    
    try:
        application = LoanApplication.objects.get(id=conflict.resource_id)
        sync = RobustOdooSync()
        sync.sync_loan_from_odoo(application)
    except Exception as e:
        logger.error(f"Error applying Odoo version to Django: {str(e)}")


@shared_task
def cleanup_expired_locks():
    """
    Clean up expired sync locks
    """
    count = SyncLock.release_all_expired()
    logger.info(f"Released {count} expired sync locks")
    return f"Released {count} locks"


@shared_task
def full_bidirectional_sync():
    """
    Perform a full bidirectional sync of all loans
    """
    from apps.loans.models import LoanApplication
    
    results = {
        'django_to_odoo': 0,
        'odoo_to_django': 0,
        'errors': []
    }
    
    try:
        sync = RobustOdooSync()
        
        # Sync Django loans to Odoo
        django_applications = LoanApplication.objects.exclude(
            status=LoanApplication.Status.DRAFT
        )
        
        for application in django_applications:
            try:
                result = sync.sync_loan_to_odoo(application)
                if result['success']:
                    results['django_to_odoo'] += 1
            except Exception as e:
                results['errors'].append(f"{application.reference_number}: {str(e)}")
        
        # Sync Odoo loans to Django
        odoo_applications = LoanApplication.objects.filter(
            odoo_application_id__isnull=False
        )
        
        for application in odoo_applications:
            try:
                result = sync.sync_loan_from_odoo(application)
                if result['success']:
                    results['odoo_to_django'] += 1
            except Exception as e:
                results['errors'].append(f"{application.reference_number}: {str(e)}")
        
        logger.info(f"Full sync completed: {results}")
        return results
        
    except Exception as e:
        logger.exception(f"Full sync failed: {str(e)}")
        return {'error': str(e)}


@shared_task
def test_robust_odoo_connection():
    """
    Test connection to Odoo
    """
    try:
        sync = RobustOdooSync()
        result = sync.test_connection()
        
        if result['status'] == 'connected':
            logger.info("Odoo connection test successful")
            return "Odoo connection test successful"
        else:
            logger.error(f"Odoo connection test failed: {result.get('error')}")
            return f"Odoo connection test failed: {result.get('error')}"
            
    except Exception as e:
        logger.error(f"Odoo connection test error: {str(e)}")
        return f"Odoo connection test error: {str(e)}"
