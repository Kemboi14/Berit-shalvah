# -*- coding: utf-8 -*-
"""
Custom user model and profile management for Berit Shalvah Financial Services
"""
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField
import uuid


class User(AbstractUser):
    """
    Custom user model extending Django's AbstractUser
    """
    class UserType(models.TextChoices):
        CLIENT = 'client', _('Client')
        STAFF = 'staff', _('Staff')
        ADMIN = 'admin', _('Admin')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(_('email address'), unique=True)
    phone = PhoneNumberField(_('phone number'), blank=True, null=True)
    user_type = models.CharField(
        _('user type'),
        max_length=10,
        choices=UserType.choices,
        default=UserType.CLIENT,
    )
    is_verified = models.BooleanField(_('email verified'), default=False)
    date_of_birth = models.DateField(_('date of birth'), blank=True, null=True)
    national_id = models.CharField(
        _('national ID'),
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        help_text=_('Kenyan National ID number (8 digits)')
    )
    kra_pin = models.CharField(
        _('KRA PIN'),
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        help_text=_('Kenya Revenue Authority PIN number')
    )
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']
    
    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['-date_joined']
    
    def __str__(self):
        return self.email
    
    @property
    def full_name(self):
        """Return the user's full name"""
        return f"{self.first_name} {self.last_name}".strip()
    
    def get_client_profile(self):
        """Get the client profile if user is a client"""
        if self.user_type == self.UserType.CLIENT:
            try:
                return self.client_profile
            except ClientProfile.DoesNotExist:
                return None
        return None
    
    def has_prior_loans(self):
        """Check if client has prior loan history"""
        if self.user_type == self.UserType.CLIENT:
            profile = self.get_client_profile()
            if profile:
                return profile.loan_applications.exists()
        return False


class ClientProfile(models.Model):
    """
    Extended profile for client users
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='client_profile',
        verbose_name=_('user')
    )
    
    class EmploymentStatus(models.TextChoices):
        EMPLOYED = 'employed', _('Employed')
        SELF_EMPLOYED = 'self_employed', _('Self-Employed')
        BUSINESS_OWNER = 'business_owner', _('Business Owner')
        UNEMPLOYED = 'unemployed', _('Unemployed')
        STUDENT = 'student', _('Student')
        RETIRED = 'retired', _('Retired')
    
    employment_status = models.CharField(
        _('employment status'),
        max_length=20,
        choices=EmploymentStatus.choices,
        blank=True
    )
    employer_name = models.CharField(_('employer name'), max_length=200, blank=True)
    employer_address = models.TextField(_('employer address'), blank=True)
    monthly_income = models.DecimalField(
        _('monthly income'),
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        help_text=_('Monthly income in KES')
    )
    residential_address = models.TextField(_('residential address'), blank=True)
    postal_address = models.CharField(_('postal address'), max_length=100, blank=True)
    city = models.CharField(_('city'), max_length=100, blank=True)
    county = models.CharField(_('county'), max_length=100, blank=True)
    
    # Banking information
    bank_name = models.CharField(_('bank name'), max_length=200, blank=True)
    bank_account_number = models.CharField(_('bank account number'), max_length=50, blank=True)
    bank_branch = models.CharField(_('bank branch'), max_length=200, blank=True)
    mpesa_phone = PhoneNumberField(_('M-Pesa phone number'), blank=True, null=True)
    
    # Verification status
    kyc_verified = models.BooleanField(_('KYC verified'), default=False)
    kyc_verified_date = models.DateTimeField(_('KYC verified date'), blank=True, null=True)
    kyc_verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='kyc_verifications',
        verbose_name=_('KYC verified by')
    )
    
    # Preferences
    email_notifications = models.BooleanField(_('email notifications'), default=True)
    sms_notifications = models.BooleanField(_('SMS notifications'), default=True)
    preferred_language = models.CharField(
        _('preferred language'),
        max_length=10,
        choices=[
            ('en', 'English'),
            ('sw', 'Swahili'),
        ],
        default='en'
    )
    
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)
    
    class Meta:
        verbose_name = _('Client Profile')
        verbose_name_plural = _('Client Profiles')
    
    def __str__(self):
        return f"{self.user.full_name} - Client Profile"
    
    def get_completion_percentage(self):
        """Calculate profile completion percentage"""
        fields_to_check = [
            self.user.phone,
            self.user.date_of_birth,
            self.user.national_id,
            self.user.kra_pin,
            self.employment_status,
            self.monthly_income,
            self.residential_address,
            self.city,
            self.county,
            self.bank_name,
            self.bank_account_number,
        ]
        
        completed_fields = sum(1 for field in fields_to_check if field)
        total_fields = len(fields_to_check)
        
        return int((completed_fields / total_fields) * 100) if total_fields > 0 else 0


class UserDocument(models.Model):
    """
    Documents uploaded by users for verification
    """
    class DocumentType(models.TextChoices):
        ID_COPY = 'id_copy', _('ID Copy')
        KRA_PIN = 'kra_pin', _('KRA PIN Certificate')
        PASSPORT_PHOTO = 'passport_photo', _('Passport Photo')
        PROOF_OF_ADDRESS = 'proof_of_address', _('Proof of Address')
        BANK_STATEMENT = 'bank_statement', _('Bank Statement')
        MPESA_STATEMENT = 'mpesa_statement', _('M-Pesa Statement')
        PAYSLIP = 'payslip', _('Payslip')
        BUSINESS_LICENSE = 'business_license', _('Business License')
        OTHER = 'other', _('Other')
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='documents',
        verbose_name=_('user')
    )
    document_type = models.CharField(
        _('document type'),
        max_length=20,
        choices=DocumentType.choices
    )
    file = models.FileField(_('file'), upload_to='documents/%Y/%m/')
    filename = models.CharField(_('filename'), max_length=255)
    file_size = models.PositiveIntegerField(_('file size'), help_text=_('File size in bytes'))
    mime_type = models.CharField(_('MIME type'), max_length=100, blank=True)
    uploaded_at = models.DateTimeField(_('uploaded at'), auto_now_add=True)
    
    # Verification
    is_verified = models.BooleanField(_('verified'), default=False)
    verified_at = models.DateTimeField(_('verified at'), blank=True, null=True)
    verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='verified_documents',
        verbose_name=_('verified by')
    )
    verification_notes = models.TextField(_('verification notes'), blank=True)
    
    # Expiry for documents that expire
    expiry_date = models.DateField(_('expiry date'), blank=True, null=True)
    
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)
    
    class Meta:
        verbose_name = _('User Document')
        verbose_name_plural = _('User Documents')
        ordering = ['-uploaded_at']
        unique_together = ['user', 'document_type']
    
    def __str__(self):
        return f"{self.user.email} - {self.get_document_type_display()}"
    
    def is_expired(self):
        """Check if document has expired"""
        if self.expiry_date:
            from django.utils import timezone
            return self.expiry_date < timezone.now().date()
        return False
    
    def get_file_size_mb(self):
        """Get file size in MB"""
        return round(self.file_size / (1024 * 1024), 2)


class VerificationRequest(models.Model):
    """
    Verification requests submitted by clients
    """
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        APPROVED = 'approved', _('Approved')
        REJECTED = 'rejected', _('Rejected')
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='verification_requests',
        verbose_name=_('user')
    )
    request_type = models.CharField(
        _('request type'),
        max_length=50,
        choices=[
            ('kyc', _('KYC Verification')),
            ('identity', _('Identity Verification')),
            ('address', _('Address Verification')),
            ('income', _('Income Verification')),
        ]
    )
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    submitted_at = models.DateTimeField(_('submitted at'), auto_now_add=True)
    reviewed_at = models.DateTimeField(_('reviewed at'), blank=True, null=True)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='reviewed_verifications',
        verbose_name=_('reviewed by')
    )
    notes = models.TextField(_('notes'), blank=True)
    rejection_reason = models.TextField(_('rejection reason'), blank=True)
    
    class Meta:
        verbose_name = _('Verification Request')
        verbose_name_plural = _('Verification Requests')
        ordering = ['-submitted_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.get_request_type_display()}"
