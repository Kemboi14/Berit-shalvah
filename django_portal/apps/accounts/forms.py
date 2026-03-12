# -*- coding: utf-8 -*-
"""
Forms for user authentication and profile management
"""
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from phonenumber_field.formfields import PhoneNumberField
from phonenumber_field.validators import validate_international_phonenumber

from .models import User, ClientProfile, UserDocument

User = get_user_model()


class CustomUserCreationForm(UserCreationForm):
    """Custom user registration form"""
    email = forms.EmailField(
        label=_('Email'),
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email',
            'autocomplete': 'email'
        })
    )
    first_name = forms.CharField(
        label=_('First Name'),
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your first name',
            'autocomplete': 'given-name'
        })
    )
    last_name = forms.CharField(
        label=_('Last Name'),
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your last name',
            'autocomplete': 'family-name'
        })
    )
    phone = PhoneNumberField(
        label=_('Phone Number'),
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+254712345678',
            'autocomplete': 'tel'
        })
    )
    national_id = forms.CharField(
        label=_('National ID Number'),
        required=True,
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your 8-digit National ID',
            'autocomplete': 'off',
            'pattern': '[0-9]{8}',
            'minlength': '8',
            'maxlength': '8'
        })
    )
    kra_pin = forms.CharField(
        label=_('KRA PIN'),
        required=True,
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your KRA PIN',
            'autocomplete': 'off'
        })
    )
    date_of_birth = forms.DateField(
        label=_('Date of Birth'),
        required=True,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'placeholder': 'YYYY-MM-DD',
            'autocomplete': 'bday'
        })
    )
    password1 = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter password',
            'autocomplete': 'new-password'
        })
    )
    password2 = forms.CharField(
        label=_('Confirm Password'),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm password',
            'autocomplete': 'new-password'
        })
    )
    terms_accepted = forms.BooleanField(
        label=_('I accept the terms and conditions'),
        required=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    
    class Meta:
        model = User
        fields = (
            'email', 'first_name', 'last_name', 'phone', 
            'national_id', 'kra_pin', 'date_of_birth',
            'password1', 'password2', 'terms_accepted'
        )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].required = False
        self.fields['username'].widget = forms.HiddenInput()
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError(_('A user with this email already exists.'))
        return email
    
    def clean_national_id(self):
        national_id = self.cleaned_data.get('national_id')
        if national_id and User.objects.filter(national_id=national_id).exists():
            raise ValidationError(_('A user with this National ID already exists.'))
        
        # Validate Kenyan ID format (8 digits)
        if national_id and not national_id.isdigit() or len(national_id) != 8:
            raise ValidationError(_('National ID must be exactly 8 digits.'))
        
        return national_id
    
    def clean_kra_pin(self):
        kra_pin = self.cleaned_data.get('kra_pin')
        if kra_pin and User.objects.filter(kra_pin=kra_pin).exists():
            raise ValidationError(_('A user with this KRA PIN already exists.'))
        return kra_pin
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            try:
                validate_international_phonenumber(str(phone))
            except ValidationError:
                raise ValidationError(_('Enter a valid phone number (e.g., +254712345678).'))
        return phone
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email  # Use email as username
        user.user_type = User.UserType.CLIENT
        if commit:
            user.save()
        return user


class UserProfileUpdateForm(forms.ModelForm):
    """Form for updating user profile"""
    phone = PhoneNumberField(
        label=_('Phone Number'),
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+254712345678'
        })
    )
    date_of_birth = forms.DateField(
        label=_('Date of Birth'),
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'phone', 'date_of_birth')
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
        }


class ClientProfileForm(forms.ModelForm):
    """Form for updating client profile"""
    monthly_income = forms.DecimalField(
        label=_('Monthly Income (KES)'),
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '0.00',
            'step': '0.01'
        })
    )
    mpesa_phone = PhoneNumberField(
        label=_('M-Pesa Phone Number'),
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+254712345678'
        })
    )
    
    class Meta:
        model = ClientProfile
        fields = (
            'employment_status', 'employer_name', 'employer_address',
            'monthly_income', 'residential_address', 'postal_address',
            'city', 'county', 'bank_name', 'bank_account_number',
            'bank_branch', 'mpesa_phone', 'email_notifications',
            'sms_notifications', 'preferred_language'
        )
        widgets = {
            'employment_status': forms.Select(attrs={'class': 'form-control'}),
            'employer_name': forms.TextInput(attrs={'class': 'form-control'}),
            'employer_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'residential_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'postal_address': forms.TextInput(attrs={'class': 'form-control'}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'county': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_branch': forms.TextInput(attrs={'class': 'form-control'}),
            'email_notifications': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sms_notifications': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'preferred_language': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def clean_monthly_income(self):
        income = self.cleaned_data.get('monthly_income')
        if income is not None and income <= 0:
            raise ValidationError(_('Monthly income must be greater than 0.'))
        return income
    
    def clean_mpesa_phone(self):
        phone = self.cleaned_data.get('mpesa_phone')
        if phone:
            try:
                validate_international_phonenumber(str(phone))
            except ValidationError:
                raise ValidationError(_('Enter a valid M-Pesa phone number (e.g., +254712345678).'))
        return phone


class UserDocumentForm(forms.ModelForm):
    """Form for uploading user documents"""
    file = forms.FileField(
        label=_('Document File'),
        required=True,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx'
        })
    )
    
    class Meta:
        model = UserDocument
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
            max_size = 20 * 1024 * 1024  # 20MB
            if file.size > max_size:
                raise ValidationError(_('File size cannot exceed 20MB.'))
            
            # Check file type
            allowed_types = ['pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx']
            file_extension = file.name.split('.')[-1].lower()
            if file_extension not in allowed_types:
                raise ValidationError(
                    _('File type not allowed. Allowed types: PDF, JPG, JPEG, PNG, DOC, DOCX.')
                )
        
        return file


class PasswordResetForm(forms.Form):
    """Custom password reset form"""
    email = forms.EmailField(
        label=_('Email'),
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address'
        })
    )
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not User.objects.filter(email=email).exists():
            raise ValidationError(_('No user found with this email address.'))
        return email


class PasswordChangeForm(forms.Form):
    """Custom password change form"""
    current_password = forms.CharField(
        label=_('Current Password'),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter current password'
        })
    )
    new_password = forms.CharField(
        label=_('New Password'),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter new password'
        })
    )
    confirm_password = forms.CharField(
        label=_('Confirm New Password'),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm new password'
        })
    )
    
    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
    
    def clean_current_password(self):
        current_password = self.cleaned_data.get('current_password')
        if not self.user.check_password(current_password):
            raise ValidationError(_('Current password is incorrect.'))
        return current_password
    
    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if new_password and confirm_password and new_password != confirm_password:
            raise ValidationError(_('New passwords do not match.'))
        
        return cleaned_data
    
    def save(self):
        new_password = self.cleaned_data.get('new_password')
        self.user.set_password(new_password)
        self.user.save()
        return self.user
