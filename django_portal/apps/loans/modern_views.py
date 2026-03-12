# -*- coding: utf-8 -*-
"""
Enhanced views for modern loan application with KYC requirements
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import CreateView, UpdateView, DetailView, ListView, TemplateView
from django.views.generic.edit import FormView
from django.http import JsonResponse, HttpResponseBadRequest
from django.urls import reverse_lazy
from django.utils import timezone
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings
import json
import uuid
import logging

from .models import LoanApplication, LoanDocument, LoanCollateral, LoanGuarantor
from .modern_forms import (
    ModernLoanApplicationForm,
    PersonalInformationForm,
    LoanDetailsForm,
    KYCDocumentsForm,
    CollateralForm,
    GuarantorForm,
    TermsAndConditionsForm,
    LoanApplicationStatusForm
)
from .utils import LoanCalculator, EnhancedOdooIntegration
from .enhanced_tasks import sync_loan_application

logger = logging.getLogger(__name__)


class ModernLoanApplicationView(LoginRequiredMixin, FormView):
    """Modern multi-step loan application view"""
    template_name = 'loans/modern_loan_application.html'
    success_url = reverse_lazy('loans:application_success')
    form_class = ModernLoanApplicationForm
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Initialize form if not exists
        if 'application_form' not in context:
            context['application_form'] = self.get_form_class()(user=self.request.user)
        
        context['today'] = timezone.now().date().strftime('%Y-%m-%d')
        return context
    
    def get_form_class(self):
        """Return form class with user parameter"""
        return ModernLoanApplicationForm
    
    def get_form_kwargs(self):
        """Add user to form kwargs"""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def post(self, request, *args, **kwargs):
        """Handle form submission with AJAX support"""
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return self.handle_ajax_submission(request)
        
        return super().post(request, *args, **kwargs)
    
    def handle_ajax_submission(self, request):
        """Handle AJAX form submission"""
        try:
            with transaction.atomic():
                # Create loan application
                application = LoanApplication.objects.create(
                    user=request.user,
                    loan_amount=float(request.POST.get('loan_amount')),
                    loan_duration=int(request.POST.get('loan_duration')),
                    loan_purpose=request.POST.get('loan_purpose'),
                    status=LoanApplication.Status.DRAFT
                )
                
                # Update calculated fields
                calculator = LoanCalculator()
                loan_details = calculator.calculate(
                    application.loan_amount,
                    application.loan_duration
                )
                
                application.interest_rate = loan_details['interest_rate']
                application.monthly_repayment = loan_details['monthly_repayment']
                application.total_repayable = loan_details['total_repayable']
                application.legal_fee = loan_details['legal_fee']
                application.collateral_required = loan_details['collateral_required']
                application.save()
                
                # Handle document uploads
                self.handle_document_uploads(request, application)
                
                # Handle collateral
                self.handle_collateral_submissions(request, application)
                
                # Handle guarantors
                self.handle_guarantor_submissions(request, application)
                
                # Update status based on completion
                if self.is_application_complete(application):
                    application.status = LoanApplication.Status.SUBMITTED
                    application.submitted_at = timezone.now()
                    application.save()
                    
                    # Queue for Odoo sync
                    sync_loan_application.delay(application.id)
                    
                    # Send confirmation email
                    self.send_application_confirmation(application)
                
                return JsonResponse({
                    'success': True,
                    'message': 'Application submitted successfully!',
                    'application_id': application.id,
                    'reference_number': application.reference_number,
                    'redirect_url': reverse_lazy('loans:application_success')
                })
                
        except Exception as e:
            logger.error(f"Error submitting loan application: {str(e)}")
            return JsonResponse({
                'success': False,
                'message': f'Error submitting application: {str(e)}'
            })
    
    def handle_document_uploads(self, request, application):
        """Handle document file uploads"""
        document_types = [
            'id_copy', 'kra_pin', 'passport_photo',
            'crb_clearance', 'bank_statement', 'payslip'
        ]
        
        for doc_type in document_types:
            # Try multiple field name formats
            files = []
            files.extend(request.FILES.getlist(doc_type))  # Standard field name
            files.extend(request.FILES.getlist(f'{doc_type}_0'))  # Indexed format
            
            for file in files:
                if file:
                    try:
                        # Generate unique filename
                        filename = f"{doc_type}_{application.reference_number}_{uuid.uuid4().hex[:8]}_{file.name}"
                        
                        # Save file
                        file_path = default_storage.save(
                            f'loan_documents/{application.reference_number}/{filename}',
                            file
                        )
                        
                        # Create document record
                        LoanDocument.objects.create(
                            loan_application=application,
                            document_type=doc_type,
                            file=file_path,
                            filename=file.name,
                            file_size=file.size,
                            mime_type=file.content_type or 'application/octet-stream',
                            is_verified=False
                        )
                        
                        logger.info(f"Successfully uploaded {doc_type} document: {filename}")
                        
                    except Exception as e:
                        logger.error(f"Error uploading {doc_type} document: {str(e)}")
                        # Continue with other files even if one fails
    
    def handle_collateral_submissions(self, request, application):
        """Handle collateral submissions"""
        collateral_count = 0
        while f'collateral_type_{collateral_count}' in request.POST:
            collateral_data = {
                'collateral_type': request.POST.get(f'collateral_type_{collateral_count}'),
                'description': request.POST.get(f'collateral_description_{collateral_count}'),
                'estimated_value': request.POST.get(f'collateral_value_{collateral_count}'),
                'valuation_date': request.POST.get(f'collateral_valuation_date_{collateral_count}'),
                'location': request.POST.get(f'collateral_location_{collateral_count}', ''),
                'serial_number': request.POST.get(f'collateral_serial_{collateral_count}', ''),
                'registration_number': request.POST.get(f'collateral_registration_{collateral_count}', ''),
                'insurance_policy': request.POST.get(f'collateral_insurance_{collateral_count}', ''),
            }
            
            # Only create if required fields are present
            if collateral_data['collateral_type'] and collateral_data['description'] and collateral_data['estimated_value']:
                LoanCollateral.objects.create(
                    loan_application=application,
                    **collateral_data
                )
            
            collateral_count += 1
    
    def handle_guarantor_submissions(self, request, application):
        """Handle guarantor submissions"""
        guarantor_count = 0
        while f'guarantor_name_{guarantor_count}' in request.POST:
            guarantor_data = {
                'name': request.POST.get(f'guarantor_name_{guarantor_count}'),
                'id_number': request.POST.get(f'guarantor_id_{guarantor_count}'),
                'phone': request.POST.get(f'guarantor_phone_{guarantor_count}'),
                'email': request.POST.get(f'guarantor_email_{guarantor_count}', ''),
                'employer_address': request.POST.get(f'guarantor_address_{guarantor_count}'),
                'relationship_to_applicant': request.POST.get(f'guarantor_relationship_{guarantor_count}'),
                'occupation': request.POST.get(f'guarantor_occupation_{guarantor_count}', ''),
                'monthly_income': request.POST.get(f'guarantor_income_{guarantor_count}'),
                'years_known': request.POST.get(f'guarantor_years_known_{guarantor_count}'),
            }
            
            # Only create if required fields are present
            if guarantor_data['name'] and guarantor_data['id_number'] and guarantor_data['phone']:
                LoanGuarantor.objects.create(
                    loan_application=application,
                    **guarantor_data
                )
            
            guarantor_count += 1
    
    def is_application_complete(self, application):
        """Check if application has all required information"""
        # Check required KYC documents
        required_docs = ['id_copy', 'kra_pin', 'passport_photo']
        uploaded_docs = set(
            application.documents.values_list('document_type', flat=True).distinct()
        )
        
        missing_docs = set(required_docs) - uploaded_docs
        if missing_docs:
            logger.warning(f"Missing required documents: {missing_docs}")
            return False
        
        # Check if loan details are complete
        if not all([application.loan_amount, application.loan_duration, application.loan_purpose]):
            logger.warning("Missing loan details")
            return False
        
        # Check if at least one collateral or guarantor is provided
        has_collateral = application.collaterals.exists()
        has_guarantor = application.guarantors.exists()
        
        if not (has_collateral or has_guarantor):
            logger.warning("No collateral or guarantor provided")
            return False
        
        logger.info("Application is complete and ready for submission")
        return True
    
    def send_application_confirmation(self, application):
        """Send application confirmation email"""
        try:
            subject = f"Loan Application Received - {application.reference_number}"
            
            context = {
                'user': application.user,
                'application': application,
                'portal_settings': getattr(settings, 'PORTAL_SETTINGS', {}),
            }
            
            html_message = render_to_string('berit/emails/application_confirmation.html', context)
            text_message = render_to_string('berit/emails/application_confirmation.txt', context)
            
            send_mail(
                subject=subject,
                message=text_message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@beritshalvah.com'),
                recipient_list=[application.user.email],
                html_message=html_message,
                fail_silently=False
            )
            
            logger.info(f"Sent application confirmation to {application.user.email}")
            
        except Exception as e:
            logger.error(f"Error sending application confirmation: {str(e)}")


class ApplicationDetailView(LoginRequiredMixin, DetailView):
    """Detailed view of loan application"""
    model = LoanApplication
    template_name = 'loans/application_detail.html'
    context_object_name = 'application'
    
    def get_queryset(self):
        return LoanApplication.objects.filter(user=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        application = self.get_object()
        
        # Get completion percentage
        context['completion_percentage'] = application.get_completion_percentage()
        
        # Check if can submit
        context['can_submit'] = application.can_submit()
        
        # Get documents
        context['documents'] = application.documents.all()
        
        # Get collaterals
        context['collaterals'] = application.collaterals.all()
        
        # Get guarantors
        context['guarantors'] = application.guarantors.all()
        
        # Get repayment schedule if available
        if application.status in ['approved', 'disbursed', 'active']:
            context['repayment_schedule'] = application.repayment_schedule.all()
        
        # Check Odoo sync status
        context['odoo_synced'] = application.odoo_application_id is not None
        
        return context


class ApplicationListView(LoginRequiredMixin, ListView):
    """List of user's loan applications"""
    model = LoanApplication
    template_name = 'loans/application_list.html'
    context_object_name = 'applications'
    paginate_by = 10
    
    def get_queryset(self):
        return LoanApplication.objects.filter(user=self.request.user).order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add status filter
        status_filter = self.request.GET.get('status')
        if status_filter:
            context['applications'] = context['applications'].filter(status=status_filter)
            context['current_status'] = status_filter
        else:
            context['current_status'] = 'all'
        
        # Add status choices for filter
        context['status_choices'] = LoanApplication.Status.choices
        
        return context


@login_required
def upload_document(request, application_id, document_type):
    """Handle individual document upload"""
    application = get_object_or_404(LoanApplication, id=application_id, user=request.user)
    
    if request.method == 'POST' and request.FILES.get('file'):
        file = request.FILES['file']
        
        # Validate file size
        if file.size > 5 * 1024 * 1024:  # 5MB
            return JsonResponse({'error': 'File size must be less than 5MB'}, status=400)
        
        # Generate unique filename
        filename = f"{document_type}_{application.reference_number}_{uuid.uuid4().hex[:8]}_{file.name}"
        
        # Save file
        file_path = default_storage.save(
            f'loan_documents/{application.reference_number}/{filename}',
            file
        )
        
        # Create document record
        document = LoanDocument.objects.create(
            loan_application=application,
            document_type=document_type,
            file=file_path,
            filename=file.name,
            file_size=file.size,
            mime_type=file.content_type or 'application/octet-stream',
            is_verified=False
        )
        
        return JsonResponse({
            'success': True,
            'document_id': document.id,
            'filename': file.name,
            'size': file.size
        })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
def delete_document(request, application_id, document_id):
    """Delete a document"""
    application = get_object_or_404(LoanApplication, id=application_id, user=request.user)
    document = get_object_or_404(LoanDocument, id=document_id, loan_application=application)
    
    if request.method == 'DELETE':
        # Delete file from storage
        if document.file:
            default_storage.delete(document.file.name)
        
        # Delete record
        document.delete()
        
        return JsonResponse({'success': True})
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
def submit_application(request, application_id):
    """Submit loan application for review"""
    application = get_object_or_404(LoanApplication, id=application_id, user=request.user)
    
    if application.status != LoanApplication.Status.DRAFT:
        return JsonResponse({'error': 'Application can only be submitted from draft status'}, status=400)
    
    if not application.can_submit():
        return JsonResponse({'error': 'Application is incomplete. Please complete all required fields.'}, status=400)
    
    try:
        with transaction.atomic():
            application.status = LoanApplication.Status.SUBMITTED
            application.submitted_at = timezone.now()
            application.save()
            
            # Queue for Odoo sync
            sync_loan_application.delay(application.id)
            
            # Send confirmation email
            from .enhanced_tasks import send_application_confirmation
            send_application_confirmation.delay(application.id)
        
        return JsonResponse({
            'success': True,
            'message': 'Application submitted successfully!',
            'status': application.status
        })
        
    except Exception as e:
        logger.error(f"Error submitting application {application_id}: {str(e)}")
        return JsonResponse({'error': 'Error submitting application'}, status=500)


@login_required
def calculate_loan_ajax(request):
    """Calculate loan details via AJAX"""
    try:
        loan_amount = float(request.GET.get('amount', 0))
        loan_duration = int(request.GET.get('duration', 0))
        
        if loan_amount < 1000 or loan_amount > 500000:
            return JsonResponse({'error': 'Invalid loan amount'}, status=400)
        
        if loan_duration not in [1, 3, 6, 9, 12]:
            return JsonResponse({'error': 'Invalid loan duration'}, status=400)
        
        calculator = LoanCalculator()
        loan_details = calculator.calculate(loan_amount, loan_duration)
        
        return JsonResponse({
            'success': True,
            'details': loan_details
        })
        
    except (ValueError, TypeError) as e:
        return JsonResponse({'error': 'Invalid parameters'}, status=400)
    except Exception as e:
        logger.error(f"Error calculating loan: {str(e)}")
        return JsonResponse({'error': 'Calculation error'}, status=500)


@login_required
def application_dashboard(request):
    """Enhanced dashboard with sync information"""
    from .sync_views import dashboard_with_sync
    return dashboard_with_sync(request)


# Staff/Admin views
class StaffApplicationListView(LoginRequiredMixin, ListView):
    """Staff view of all loan applications"""
    model = LoanApplication
    template_name = 'loans/staff_application_list.html'
    context_object_name = 'applications'
    paginate_by = 20
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('loans:application_list')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        queryset = LoanApplication.objects.all().order_by('-created_at')
        
        # Apply filters
        status_filter = self.request.GET.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        date_from = self.request.GET.get('date_from')
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        
        date_to = self.request.GET.get('date_to')
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add filter values
        context['status_filter'] = self.request.GET.get('status', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        context['status_choices'] = LoanApplication.Status.choices
        
        # Add statistics
        context['total_applications'] = LoanApplication.objects.count()
        context['pending_applications'] = LoanApplication.objects.filter(
            status__in=['submitted', 'under_review']
        ).count()
        context['approved_applications'] = LoanApplication.objects.filter(
            status='approved'
        ).count()
        context['active_loans'] = LoanApplication.objects.filter(
            status='active'
        ).count()
        
        return context


class StaffApplicationDetailView(LoginRequiredMixin, DetailView):
    """Staff detailed view of loan application"""
    model = LoanApplication
    template_name = 'loans/staff_application_detail.html'
    context_object_name = 'application'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('loans:application_list')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        application = self.get_object()
        
        # Add related objects
        context['documents'] = application.documents.all()
        context['collaterals'] = application.collaterals.all()
        context['guarantors'] = application.guarantors.all()
        context['repayment_schedule'] = application.repayment_schedule.all()
        
        # Add status update form
        context['status_form'] = LoanApplicationStatusForm(instance=application)
        
        # Add Odoo sync info
        context['odoo_synced'] = application.odoo_application_id is not None
        
        return context


@login_required
def update_application_status(request, application_id):
    """Update application status (staff only)"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    application = get_object_or_404(LoanApplication, id=application_id)
    
    if request.method == 'POST':
        form = LoanApplicationStatusForm(request.POST, instance=application)
        if form.is_valid():
            old_status = application.status
            form.save()
            
            # Sync to Odoo if status changed
            if old_status != application.status:
                from .enhanced_tasks import sync_loan_application
                sync_loan_application.delay(application.id)
                
                # Send notification to user
                from .enhanced_tasks import send_status_change_notification
                send_status_change_notification.delay(
                    application.id, old_status, application.status
                )
            
            return JsonResponse({
                'success': True,
                'message': 'Status updated successfully',
                'new_status': application.status
            })
        else:
            return JsonResponse({
                'success': False,
                'errors': form.errors
            }, status=400)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
def verify_document(request, application_id, document_id):
    """Verify a document (staff only)"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    application = get_object_or_404(LoanApplication, id=application_id)
    document = get_object_or_404(LoanDocument, id=document_id, loan_application=application)
    
    if request.method == 'POST':
        verified = request.POST.get('verified') == 'true'
        notes = request.POST.get('notes', '')
        
        document.is_verified = verified
        document.verification_notes = notes
        if verified:
            document.verified_at = timezone.now()
        document.save()
        
        return JsonResponse({
            'success': True,
            'verified': verified,
            'verified_at': document.verified_at
        })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
def verify_collateral(request, application_id, collateral_id):
    """Verify collateral (staff only)"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    application = get_object_or_404(LoanApplication, id=application_id)
    collateral = get_object_or_404(LoanCollateral, id=collateral_id, loan_application=application)
    
    if request.method == 'POST':
        verified = request.POST.get('verified') == 'true'
        notes = request.POST.get('notes', '')
        
        collateral.is_verified = verified
        collateral.verification_notes = notes
        if verified:
            collateral.verified_at = timezone.now()
        collateral.save()
        
        return JsonResponse({
            'success': True,
            'verified': verified,
            'verified_at': collateral.verified_at
        })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
def verify_guarantor(request, application_id, guarantor_id):
    """Verify guarantor (staff only)"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    application = get_object_or_404(LoanApplication, id=application_id)
    guarantor = get_object_or_404(LoanGuarantor, id=guarantor_id, loan_application=application)
    
    if request.method == 'POST':
        verified = request.POST.get('verified') == 'true'
        notes = request.POST.get('notes', '')
        
        guarantor.is_verified = verified
        guarantor.verification_notes = notes
        if verified:
            guarantor.verified_at = timezone.now()
        guarantor.save()
        
        return JsonResponse({
            'success': True,
            'verified': verified,
            'verified_at': guarantor.verified_at
        })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


class ApplicationSuccessView(LoginRequiredMixin, TemplateView):
    """Application success page"""
    template_name = 'loans/application_success.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add any additional context if needed
        return context


@login_required
def application_success(request):
    """Application success page"""
    return render(request, 'loans/application_success.html')


@login_required
def application_wizard(request):
    """Simplified application wizard for mobile"""
    if request.method == 'POST':
        # Handle simplified form submission
        return redirect('loans:application_success')
    
    return render(request, 'loans/application_wizard.html')
