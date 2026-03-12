# -*- coding: utf-8 -*-
"""
Forms for loan application management
"""
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from decimal import Decimal

from .models import (
    LoanApplication, LoanDocument, LoanCollateral, 
    LoanGuarantor, RepaymentSchedule
)


class LoanApplicationForm(forms.ModelForm):
    """Form for loan application"""
    class Meta:
        model = LoanApplication
        fields = ('loan_amount', 'loan_duration', 'loan_purpose')
        widgets = {
            'loan_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter loan amount',
                'min': '1000',
                'step': '0.01'
            }),
            'loan_duration': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter duration in months',
                'min': '1',
                'max': '12'
            }),
            'loan_purpose': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Describe the purpose of this loan',
                'rows': 3
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Set max duration based on user's loan history
        if self.user and hasattr(self.user, 'has_prior_loans') and self.user.has_prior_loans():
            loan_config = getattr(settings, 'LOAN_CONFIG', {})
            max_duration = loan_config.get('max_duration_months_returning', 12)
        else:
            loan_config = getattr(settings, 'LOAN_CONFIG', {})
            max_duration = loan_config.get('max_duration_months_new', 3)
        
        self.fields['loan_duration'].widget.attrs['max'] = max_duration
        
        # Set max loan amount
        max_amount = loan_config.get('max_amount', 5000000)
        self.fields['loan_amount'].widget.attrs['max'] = max_amount
    
    def clean_loan_amount(self):
        loan_amount = self.cleaned_data.get('loan_amount')
        
        if loan_amount:
            loan_config = getattr(settings, 'LOAN_CONFIG', {})
            min_amount = loan_config.get('min_amount', 1000)
            max_amount = loan_config.get('max_amount', 5000000)
            
            if loan_amount < min_amount:
                raise ValidationError(f'Loan amount must be at least KES {min_amount:,}.')
            
            if loan_amount > max_amount:
                raise ValidationError(f'Loan amount cannot exceed KES {max_amount:,}.')
        
        return loan_amount
    
    def clean_loan_duration(self):
        loan_duration = self.cleaned_data.get('loan_duration')
        
        if loan_duration:
            # Check user's loan history
            if self.user and hasattr(self.user, 'has_prior_loans') and self.user.has_prior_loans():
                loan_config = getattr(settings, 'LOAN_CONFIG', {})
                max_duration = loan_config.get('max_duration_months_returning', 12)
            else:
                loan_config = getattr(settings, 'LOAN_CONFIG', {})
                max_duration = loan_config.get('max_duration_months_new', 3)
            
            if loan_duration > max_duration:
                if max_duration == 3:
                    raise ValidationError('First-time applicants can only apply for loans up to 3 months.')
                else:
                    raise ValidationError(f'Loan duration cannot exceed {max_duration} months.')
        
        return loan_duration


class LoanDocumentForm(forms.ModelForm):
    """Form for uploading loan documents"""
    file = forms.FileField(
        label=_('Document File'),
        required=True,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx'
        })
    )
    
    class Meta:
        model = LoanDocument
        fields = ('document_type', 'file', 'expiry_date')
        widgets = {
            'document_type': forms.Select(attrs={'class': 'form-control'}),
            'expiry_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
        }
    
    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            # Check file size (20MB limit)
            max_size = getattr(settings, 'MAX_UPLOAD_SIZE', 20 * 1024 * 1024)  # 20MB
            if file.size > max_size:
                raise ValidationError(f'File size cannot exceed {max_size // (1024*1024)}MB.')
            
            # Check file type
            allowed_types = getattr(settings, 'ALLOWED_DOCUMENT_TYPES', 
                                  ['pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx'])
            file_extension = file.name.split('.')[-1].lower()
            if file_extension not in allowed_types:
                raise ValidationError(
                    f'File type not allowed. Allowed types: {", ".join(allowed_types).upper()}.'
                )
        
        return file


class LoanCollateralForm(forms.ModelForm):
    """Form for adding collateral"""
    class Meta:
        model = LoanCollateral
        fields = (
            'collateral_type', 'description', 'estimated_value', 'valuation_date',
            'location', 'serial_number', 'registration_number', 'insurance_policy',
            'valuation_document', 'ownership_proof'
        )
        widgets = {
            'collateral_type': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'estimated_value': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter estimated value',
                'step': '0.01'
            }),
            'valuation_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'location': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'serial_number': forms.TextInput(attrs={'class': 'form-control'}),
            'registration_number': forms.TextInput(attrs={'class': 'form-control'}),
            'insurance_policy': forms.TextInput(attrs={'class': 'form-control'}),
            'valuation_document': forms.FileInput(attrs={'class': 'form-control'}),
            'ownership_proof': forms.FileInput(attrs={'class': 'form-control'}),
        }
    
    def clean_estimated_value(self):
        estimated_value = self.cleaned_data.get('estimated_value')
        
        if estimated_value and estimated_value <= 0:
            raise ValidationError('Estimated value must be greater than 0.')
        
        return estimated_value
    
    def clean_valuation_document(self):
        valuation_document = self.cleaned_data.get('valuation_document')
        
        if valuation_document:
            # Check file size
            max_size = getattr(settings, 'MAX_UPLOAD_SIZE', 20 * 1024 * 1024)
            if valuation_document.size > max_size:
                raise ValidationError(f'File size cannot exceed {max_size // (1024*1024)}MB.')
        
        return valuation_document
    
    def clean_ownership_proof(self):
        ownership_proof = self.cleaned_data.get('ownership_proof')
        
        if ownership_proof:
            # Check file size
            max_size = getattr(settings, 'MAX_UPLOAD_SIZE', 20 * 1024 * 1024)
            if ownership_proof.size > max_size:
                raise ValidationError(f'File size cannot exceed {max_size // (1024*1024)}MB.')
        
        return ownership_proof


class LoanGuarantorForm(forms.ModelForm):
    """Form for adding guarantor"""
    class Meta:
        model = LoanGuarantor
        fields = (
            'name', 'id_number', 'phone', 'email', 'employer_address',
            'relationship_to_applicant', 'occupation', 'monthly_income',
            'years_known', 'guarantee_letter', 'bank_statement', 'id_copy'
        )
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'id_number': forms.TextInput(attrs={
                'class': 'form-control',
                'pattern': '[0-9]{8}',
                'minlength': '8',
                'maxlength': '8'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+254712345678'
            }),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'employer_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'relationship_to_applicant': forms.Select(attrs={'class': 'form-control'}),
            'occupation': forms.TextInput(attrs={'class': 'form-control'}),
            'monthly_income': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter monthly income',
                'step': '0.01'
            }),
            'years_known': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '50'
            }),
            'guarantee_letter': forms.FileInput(attrs={'class': 'form-control'}),
            'bank_statement': forms.FileInput(attrs={'class': 'form-control'}),
            'id_copy': forms.FileInput(attrs={'class': 'form-control'}),
        }
    
    def clean_id_number(self):
        id_number = self.cleaned_data.get('id_number')
        
        if id_number:
            # Validate Kenyan ID format (8 digits)
            if not id_number.isdigit() or len(id_number) != 8:
                raise ValidationError('National ID must be exactly 8 digits.')
        
        return id_number
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        
        if phone:
            # Validate Kenyan phone number format
            if not (phone.startswith('+2547') and len(phone) == 13):
                raise ValidationError('Enter a valid Kenyan phone number (e.g., +254712345678).')
        
        return phone
    
    def clean_monthly_income(self):
        monthly_income = self.cleaned_data.get('monthly_income')
        
        if monthly_income is not None and monthly_income <= 0:
            raise ValidationError('Monthly income must be greater than 0.')
        
        return monthly_income
    
    def clean_guarantee_letter(self):
        guarantee_letter = self.cleaned_data.get('guarantee_letter')
        
        if guarantee_letter:
            # Check file size
            max_size = getattr(settings, 'MAX_UPLOAD_SIZE', 20 * 1024 * 1024)
            if guarantee_letter.size > max_size:
                raise ValidationError(f'File size cannot exceed {max_size // (1024*1024)}MB.')
        
        return guarantee_letter
    
    def clean_bank_statement(self):
        bank_statement = self.cleaned_data.get('bank_statement')
        
        if bank_statement:
            # Check file size
            max_size = getattr(settings, 'MAX_UPLOAD_SIZE', 20 * 1024 * 1024)
            if bank_statement.size > max_size:
                raise ValidationError(f'File size cannot exceed {max_size // (1024*1024)}MB.')
        
        return bank_statement
    
    def clean_id_copy(self):
        id_copy = self.cleaned_data.get('id_copy')
        
        if id_copy:
            # Check file size
            max_size = getattr(settings, 'MAX_UPLOAD_SIZE', 20 * 1024 * 1024)
            if id_copy.size > max_size:
                raise ValidationError(f'File size cannot exceed {max_size // (1024*1024)}MB.')
        
        return id_copy


class RepaymentScheduleForm(forms.ModelForm):
    """Form for updating repayment schedule (admin use)"""
    class Meta:
        model = RepaymentSchedule
        fields = ('amount_paid', 'payment_date', 'payment_method', 'payment_reference', 'notes')
        widgets = {
            'amount_paid': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'payment_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'payment_method': forms.Select(attrs={'class': 'form-control'}),
            'payment_reference': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class LoanSearchForm(forms.Form):
    """Form for searching loan applications"""
    query = forms.CharField(
        label=_('Search'),
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by reference number...'
        })
    )
    status = forms.ChoiceField(
        label=_('Status'),
        required=False,
        choices=[('', 'All Status')] + list(LoanApplication.Status.choices),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    date_from = forms.DateField(
        label=_('From'),
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    date_to = forms.DateField(
        label=_('To'),
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')
        
        if date_from and date_to and date_from > date_to:
            raise ValidationError('From date cannot be after to date.')
        
        return cleaned_data
