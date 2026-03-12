# -*- coding: utf-8 -*-
"""
Forms for document management
"""
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import UploadedDocument, DocumentCategory


class UploadedDocumentForm(forms.ModelForm):
    """Form for uploading documents"""
    file = forms.FileField(
        label=_('Document File'),
        required=True,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx'
        })
    )
    
    class Meta:
        model = UploadedDocument
        fields = ('title', 'description', 'category', 'file', 'is_public', 'tags')
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'tags': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter tags separated by commas'
            }),
        }
    
    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            # Check file size
            max_size = getattr(settings, 'MAX_UPLOAD_SIZE', 20 * 1024 * 1024)  # 20MB
            if file.size > max_size:
                raise ValidationError(f'File size cannot exceed {max_size // (1024*1024)}MB.')
            
            # Check file type
            allowed_types = getattr(settings, 'ALLOWED_DOCUMENT_TYPES', 
                                  ['pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx', 'xls', 'xlsx'])
            file_extension = file.name.split('.')[-1].lower()
            if file_extension not in allowed_types:
                raise ValidationError(
                    f'File type not allowed. Allowed types: {", ".join(allowed_types).upper()}.'
                )
        
        return file


class DocumentCategoryForm(forms.ModelForm):
    """Form for document categories"""
    class Meta:
        model = DocumentCategory
        fields = ('name', 'description')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def clean_name(self):
        name = self.cleaned_data.get('name')
        if DocumentCategory.objects.filter(name__iexact=name).exists():
            raise ValidationError('A category with this name already exists.')
        return name


class DocumentSearchForm(forms.Form):
    """Form for searching documents"""
    search = forms.CharField(
        label=_('Search'),
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search documents...'
        })
    )
    category = forms.ModelChoiceField(
        label=_('Category'),
        required=False,
        queryset=DocumentCategory.objects.all(),
        empty_label=_('All Categories'),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    tags = forms.CharField(
        label=_('Tags'),
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Filter by tags...'
        })
    )


class DocumentShareForm(forms.Form):
    """Form for sharing documents"""
    emails = forms.CharField(
        label=_('Share with (emails)'),
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Enter email addresses, separated by commas'
        })
    )
    make_public = forms.BooleanField(
        label=_('Make public (accessible to staff)'),
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    def clean_emails(self):
        emails = self.cleaned_data.get('emails', '')
        if emails:
            email_list = [email.strip() for email in emails.split(',')]
            for email in email_list:
                if email and '@' not in email:
                    raise ValidationError(f'Invalid email address: {email}')
        return emails
