# -*- coding: utf-8 -*-
"""
Enhanced robust synchronization with retry logic, conflict resolution, and complete data sync
"""
import xmlrpc.client
import json
import logging
import time
import base64
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

from .webhook_models import SyncEvent, SyncLock, SyncConflict

logger = logging.getLogger(__name__)


class RobustOdooSync:
    """
    Robust Odoo synchronization with retry logic and conflict resolution
    """
    
    # Retry configuration
    MAX_RETRIES = 3
    INITIAL_DELAY = 1  # seconds
    BACKOFF_FACTOR = 2
    
    def __init__(self):
        self.odoo_url = getattr(settings, 'ODOO_URL', 'http://localhost:8069')
        self.odoo_db = getattr(settings, 'ODOO_DB', 'berit_odoo')
        self.odoo_username = getattr(settings, 'ODOO_USERNAME', 'admin')
        self.odoo_password = getattr(settings, 'ODOO_PASSWORD', 'admin')
        
        self.common = None
        self.models = None
        self.uid = None
        self._connect()
    
    def _connect(self):
        """Establish connection to Odoo with retry logic"""
        for attempt in range(self.MAX_RETRIES):
            try:
                self.common = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/common')
                self.models = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/object')
                
                self.uid = self.common.authenticate(
                    self.odoo_db,
                    self.odoo_username,
                    self.odoo_password,
                    {}
                )
                
                if self.uid:
                    logger.info(f"Successfully connected to Odoo (UID: {self.uid})")
                    return
                    
            except Exception as e:
                logger.warning(f"Connection attempt {attempt + 1} failed: {str(e)}")
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.INITIAL_DELAY * (self.BACKOFF_FACTOR ** attempt)
                    logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
        
        raise Exception("Failed to connect to Odoo after multiple attempts")
    
    def _execute_with_retry(self, method, *args, **kwargs):
        """Execute Odoo method with retry logic"""
        last_error = None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                # Reconnect if needed
                if not self.uid:
                    self._connect()
                
                return method(*args, **kwargs)
                
            except xmlrpc.client.Fault as e:
                last_error = e
                logger.warning(f"Odoo XMLRPC fault (attempt {attempt + 1}): {str(e)}")
                
            except Exception as e:
                last_error = e
                logger.warning(f"Odoo call failed (attempt {attempt + 1}): {str(e)}")
                # Reconnect on failure
                self.uid = None
                self._connect()
            
            if attempt < self.MAX_RETRIES - 1:
                delay = self.INITIAL_DELAY * (self.BACKOFF_FACTOR ** attempt)
                time.sleep(delay)
        
        raise last_error
    
    def sync_loan_to_odoo(self, application, create_event=True):
        """
        Sync a loan application to Odoo with full data including documents
        """
        from apps.loans.models import LoanApplication, LoanDocument, LoanCollateral, LoanGuarantor
        
        # Acquire lock
        if not SyncLock.acquire(
            SyncLock.LockType.LOAN_APPLICATION,
            str(application.id),
            'sync_to_odoo'
        ):
            return {'success': False, 'error': 'Resource is locked'}
        
        try:
            # Create sync event
            event = None
            if create_event:
                event = SyncEvent.objects.create(
                    event_type=SyncEvent.EventType.LOAN_CREATED if not application.odoo_application_id else SyncEvent.EventType.LOAN_UPDATED,
                    direction=SyncEvent.Direction.DJANGO_TO_ODOO,
                    status=SyncEvent.Status.PENDING,
                    payload={
                        'reference_number': application.reference_number,
                        'loan_amount': str(application.loan_amount),
                        'status': application.status,
                    },
                    loan_application_id=application.id,
                    source_timestamp=timezone.now()
                )
            
            try:
                # Get or create partner
                partner_id = self._get_or_create_partner(application.user)
                
                # Prepare loan data
                loan_data = self._prepare_loan_data(application, partner_id)
                
                if application.odoo_application_id:
                    # Update existing
                    self._execute_with_retry(
                        self.models.execute_kw,
                        self.odoo_db, self.uid, self.odoo_password,
                        'berit.loan.application', 'write',
                        [[application.odoo_application_id], loan_data]
                    )
                    odoo_id = application.odoo_application_id
                else:
                    # Create new
                    odoo_id = self._execute_with_retry(
                        self.models.execute_kw,
                        self.odoo_db, self.uid, self.odoo_password,
                        'berit.loan.application', 'create',
                        [loan_data]
                    )
                
                # Update Django with Odoo ID
                application.odoo_application_id = odoo_id
                application.save()
                
                # Sync documents (full data with files)
                self._sync_documents(application, odoo_id)
                
                # Sync collaterals
                self._sync_collaterals(application, odoo_id)
                
                # Sync guarantors
                self._sync_guarantors(application, odoo_id)
                
                if event:
                    event.odoo_record_id = odoo_id
                    event.mark_completed({
                        'odoo_id': odoo_id,
                        'message': 'Loan synced successfully'
                    })
                
                return {'success': True, 'odoo_id': odoo_id}
                
            except Exception as e:
                error_msg = str(e)
                logger.exception(f"Error syncing loan to Odoo: {error_msg}")
                
                if event:
                    event.mark_failed(error_msg)
                
                return {'success': False, 'error': error_msg}
                
        finally:
            # Release lock
            SyncLock.objects.filter(
                lock_type=SyncLock.LockType.LOAN_APPLICATION,
                resource_id=str(application.id)
            ).update(is_released=True)
    
    def _prepare_loan_data(self, application, partner_id):
        """Prepare loan application data for Odoo"""
        return {
            'name': application.reference_number,
            'applicant_id': partner_id,
            'loan_amount': float(application.loan_amount),
            'loan_duration': application.loan_duration,
            'loan_purpose': application.loan_purpose or '',
            'interest_rate': float(application.interest_rate),
            'monthly_repayment': float(application.monthly_repayment),
            'total_repayable': float(application.total_repayable),
            'legal_fee': float(application.legal_fee),
            'collateral_required': float(application.collateral_required),
            'state': self._map_django_status_to_odoo(application.status),
            'application_date': application.created_at.strftime('%Y-%m-%d'),
            'portal_application_ref': application.reference_number,
            'kyc_verified': application.kyc_verified,
            'crb_cleared': application.crb_cleared,
            'notes': application.notes or '',
            'rejection_reason': application.rejection_reason or '',
        }
    
    def _sync_documents(self, application, odoo_id):
        """Sync documents to Odoo including file content"""
        from apps.loans.models import LoanDocument
        
        # Get existing Odoo documents
        odoo_docs = self._execute_with_retry(
            self.models.execute_kw,
            self.odoo_db, self.uid, self.odoo_password,
            'berit.loan.document', 'search_read',
            [[['loan_id', '=', odoo_id]]],
            {'fields': ['document_type', 'filename']}
        )
        
        odoo_doc_types = {doc['document_type']: doc['id'] for doc in odoo_docs}
        
        for doc in application.documents.all():
            try:
                doc_data = {
                    'loan_id': odoo_id,
                    'document_type': doc.document_type,
                    'filename': doc.filename,
                    'file_size': doc.file_size,
                    'upload_date': doc.uploaded_at.strftime('%Y-%m-%d'),
                    'verified': doc.is_verified,
                    'notes': doc.verification_notes or '',
                }
                
                # Add file content if exists
                if doc.file:
                    try:
                        with doc.file.open('rb') as f:
                            file_content = base64.b64encode(f.read()).decode('utf-8')
                            doc_data['file_content'] = file_content
                    except Exception as e:
                        logger.warning(f"Could not read file for {doc.filename}: {e}")
                
                if doc.document_type in odoo_doc_types:
                    # Update existing
                    self._execute_with_retry(
                        self.models.execute_kw,
                        self.odoo_db, self.uid, self.odoo_password,
                        'berit.loan.document', 'write',
                        [[odoo_doc_types[doc.document_type]], doc_data]
                    )
                else:
                    # Create new
                    self._execute_with_retry(
                        self.models.execute_kw,
                        self.odoo_db, self.uid, self.odoo_password,
                        'berit.loan.document', 'create',
                        [doc_data]
                    )
                    
            except Exception as e:
                logger.warning(f"Error syncing document {doc.filename}: {e}")
    
    def _sync_collaterals(self, application, odoo_id):
        """Sync collaterals to Odoo"""
        odoo_collaterals = self._execute_with_retry(
            self.models.execute_kw,
            self.odoo_db, self.uid, self.odoo_password,
            'berit.collateral', 'search_read',
            [[['loan_id', '=', odoo_id]]],
            {'fields': ['collateral_type', 'description']}
        )
        
        odoo_collateral_map = {
            (c['collateral_type'], c.get('description', '')): c['id'] 
            for c in odoo_collaterals
        }
        
        for collateral in application.collaterals.all():
            collateral_data = {
                'loan_id': odoo_id,
                'collateral_type': collateral.collateral_type,
                'description': collateral.description,
                'estimated_value': float(collateral.estimated_value),
                'valuation_date': collateral.valuation_date.strftime('%Y-%m-%d'),
                'location': collateral.location or '',
                'serial_number': collateral.serial_number or '',
                'registration_number': collateral.registration_number or '',
                'is_verified': collateral.is_verified,
                'notes': collateral.verification_notes or '',
            }
            
            key = (collateral.collateral_type, collateral.description)
            if key in odoo_collateral_map:
                self._execute_with_retry(
                    self.models.execute_kw,
                    self.odoo_db, self.uid, self.odoo_password,
                    'berit.collateral', 'write',
                    [[odoo_collateral_map[key]], collateral_data]
                )
            else:
                self._execute_with_retry(
                    self.models.execute_kw,
                    self.odoo_db, self.uid, self.odoo_password,
                    'berit.collateral', 'create',
                    [collateral_data]
                )
    
    def _sync_guarantors(self, application, odoo_id):
        """Sync guarantors to Odoo"""
        odoo_guarantors = self._execute_with_retry(
            self.models.execute_kw,
            self.odoo_db, self.uid, self.odoo_password,
            'berit.guarantor', 'search_read',
            [[['loan_id', '=', odoo_id]]],
            {'fields': ['id_number']}
        )
        
        odoo_guarantor_ids = {g['id_number']: g['id'] for g in odoo_guarantors}
        
        for guarantor in application.guarantors.all():
            # Get or create partner for guarantor
            guarantor_partner_id = self._get_or_create_guarantor_partner(guarantor)
            
            guarantor_data = {
                'loan_id': odoo_id,
                'partner_id': guarantor_partner_id,
                'name': guarantor.name,
                'id_number': guarantor.id_number,
                'phone': guarantor.phone,
                'email': guarantor.email or '',
                'employer_address': guarantor.employer_address,
                'relationship_to_applicant': guarantor.relationship_to_applicant or 'other',
                'occupation': guarantor.occupation or '',
                'monthly_income': float(guarantor.monthly_income) if guarantor.monthly_income else 0,
                'years_known': guarantor.years_known or 0,
                'is_verified': guarantor.is_verified,
                'notes': guarantor.verification_notes or '',
            }
            
            if guarantor.id_number in odoo_guarantor_ids:
                self._execute_with_retry(
                    self.models.execute_kw,
                    self.odoo_db, self.uid, self.odoo_password,
                    'berit.guarantor', 'write',
                    [[odoo_guarantor_ids[guarantor.id_number]], guarantor_data]
                )
            else:
                self._execute_with_retry(
                    self.models.execute_kw,
                    self.odoo_db, self.uid, self.odoo_password,
                    'berit.guarantor', 'create',
                    [guarantor_data]
                )
    
    def sync_loan_from_odoo(self, application):
        """
        Sync loan from Odoo to Django with conflict detection
        """
        if not application.odoo_application_id:
            return {'success': False, 'error': 'No Odoo ID'}
        
        if not SyncLock.acquire(
            SyncLock.LockType.LOAN_APPLICATION,
            str(application.id),
            'sync_from_odoo'
        ):
            return {'success': False, 'error': 'Resource is locked'}
        
        try:
            # Get Odoo data
            odoo_data = self._execute_with_retry(
                self.models.execute_kw,
                self.odoo_db, self.uid, self.odoo_password,
                'berit.loan.application', 'read',
                [application.odoo_application_id],
                {'fields': [
                    'name', 'state', 'loan_amount', 'loan_duration',
                    'interest_rate', 'monthly_repayment', 'total_repayable',
                    'kyc_verified', 'crb_cleared', 'notes', 'rejection_reason',
                    'approval_date', 'disbursement_date', 'write_date'
                ]}
            )
            
            if not odoo_data:
                return {'success': False, 'error': 'Odoo record not found'}
            
            odoo_record = odoo_data[0]
            
            # Check for conflicts
            conflict_detected = self._check_for_conflicts(application, odoo_record)
            
            if conflict_detected:
                return {
                    'success': False,
                    'conflict': True,
                    'message': 'Conflict detected'
                }
            
            # Update Django with Odoo data
            self._apply_odoo_data(application, odoo_record)
            
            return {'success': True, 'message': 'Synced from Odoo'}
            
        finally:
            SyncLock.objects.filter(
                lock_type=SyncLock.LockType.LOAN_APPLICATION,
                resource_id=str(application.id)
            ).update(is_released=True)
    
    def _check_for_conflicts(self, application, odoo_record):
        """Check for conflicts between Django and Odoo data"""
        # Fields to check for conflicts
        check_fields = ['loan_amount', 'loan_duration', 'notes']
        
        conflicts = []
        for field in check_fields:
            django_value = getattr(application, field, None)
            odoo_value = odoo_record.get(field)
            
            if django_value and odoo_value:
                if str(django_value) != str(odoo_value):
                    conflicts.append(field)
        
        if conflicts:
            # Create conflict record
            SyncConflict.objects.create(
                resource_type='loan_application',
                resource_id=str(application.id),
                django_data={
                    field: str(getattr(application, field)) for field in conflicts
                },
                odoo_data={field: odoo_record.get(field) for field in conflicts},
                conflict_fields=conflicts,
                django_modified_at=application.updated_at,
                odoo_modified_at=odoo_record.get('write_date', timezone.now())
            )
            return True
        
        return False
    
    def _apply_odoo_data(self, application, odoo_record):
        """Apply Odoo data to Django application"""
        status_mapping = {
            'draft': application.Status.DRAFT,
            'submitted': application.Status.SUBMITTED,
            'under_review': application.Status.UNDER_REVIEW,
            'approved': application.Status.APPROVED,
            'rejected': application.Status.REJECTED,
            'disbursed': application.Status.DISBURSED,
            'active': application.Status.ACTIVE,
            'closed': application.Status.CLOSED,
            'defaulted': application.Status.DEFAULTED,
        }
        
        if 'state' in odoo_record:
            new_status = status_mapping.get(odoo_record['state'])
            if new_status and new_status != application.status:
                application.status = new_status
        
        field_mapping = {
            'loan_amount': 'loan_amount',
            'loan_duration': 'loan_duration',
            'interest_rate': 'interest_rate',
            'monthly_repayment': 'monthly_repayment',
            'total_repayable': 'total_repayable',
            'kyc_verified': 'kyc_verified',
            'crb_cleared': 'crb_cleared',
            'notes': 'notes',
            'rejection_reason': 'rejection_reason',
        }
        
        for odoo_field, django_field in field_mapping.items():
            if odoo_field in odoo_record:
                setattr(application, django_field, odoo_record[odoo_field])
        
        application.save()
    
    def _get_or_create_partner(self, user):
        """Get or create partner in Odoo"""
        partners = self._execute_with_retry(
            self.models.execute_kw,
            self.odoo_db, self.uid, self.odoo_password,
            'res.partner', 'search',
            [[['email', '=', user.email]]]
        )
        
        if partners:
            return partners[0]
        
        partner_data = {
            'name': user.full_name,
            'email': user.email,
            'phone': str(user.phone) if user.phone else '',
            'is_company': False,
            'customer_rank': 1,
        }
        
        return self._execute_with_retry(
            self.models.execute_kw,
            self.odoo_db, self.uid, self.odoo_password,
            'res.partner', 'create',
            [partner_data]
        )
    
    def _get_or_create_guarantor_partner(self, guarantor):
        """Get or create guarantor partner in Odoo"""
        partners = self._execute_with_retry(
            self.models.execute_kw,
            self.odoo_db, self.uid, self.odoo_password,
            'res.partner', 'search',
            [[['phone', '=', guarantor.phone]]]
        )
        
        if partners:
            return partners[0]
        
        partner_data = {
            'name': guarantor.name,
            'phone': guarantor.phone,
            'email': guarantor.email or '',
            'is_company': False,
        }
        
        return self._execute_with_retry(
            self.models.execute_kw,
            self.odoo_db, self.uid, self.odoo_password,
            'res.partner', 'create',
            [partner_data]
        )
    
    def _map_django_status_to_odoo(self, django_status):
        """Map Django status to Odoo status"""
        mapping = {
            'draft': 'draft',
            'submitted': 'submitted',
            'under_review': 'under_review',
            'approved': 'approved',
            'rejected': 'rejected',
            'disbursed': 'disbursed',
            'active': 'active',
            'closed': 'closed',
            'defaulted': 'defaulted',
        }
        return mapping.get(django_status, 'draft')
    
    def test_connection(self):
        """Test connection to Odoo"""
        try:
            version = self.common.version()
            return {
                'status': 'connected',
                'version': version,
                'uid': self.uid
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
