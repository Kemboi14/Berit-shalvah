# -*- coding: utf-8 -*-
"""
Custom login form with phone number requirement
"""
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _
from phonenumber_field.formfields import PhoneNumberField
from phonenumber_field.validators import validate_international_phonenumber


class CustomAuthenticationForm(AuthenticationForm):
    """Custom login form that accepts email/username and phone"""
    login_field = forms.CharField(
        label=_('Email or Phone'),
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter email or phone number',
            'autocomplete': 'username'
        })
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove the username field and use our custom login_field
        if 'username' in self.fields:
            del self.fields['username']
    
    def clean_login_field(self):
        login_field = self.cleaned_data.get('login_field')
        if not login_field:
            raise forms.ValidationError(_('Please enter your email or phone number.'))
        return login_field
    
    def get_username(self):
        return self.cleaned_data.get('login_field')


class PhoneLoginForm(forms.Form):
    """Phone number based login form"""
    phone = PhoneNumberField(
        label=_('Phone Number'),
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+254712345678',
            'autocomplete': 'tel'
        })
    )
    password = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password'
        })
    )
    
    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            try:
                validate_international_phonenumber(str(phone))
            except forms.ValidationError:
                raise forms.ValidationError(_('Enter a valid phone number (e.g., +254712345678).'))
        return phone


class EmailLoginForm(forms.Form):
    """Email based login form"""
    email = forms.EmailField(
        label=_('Email Address'),
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address',
            'autocomplete': 'email'
        })
    )
    password = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password'
        })
    )
