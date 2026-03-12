# -*- coding: utf-8 -*-
"""
Admin configuration for accounts app
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User, ClientProfile, UserDocument, VerificationRequest


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom user admin"""
    list_display = ('email', 'full_name', 'user_type', 'is_verified', 'is_active', 'date_joined')
    list_filter = ('user_type', 'is_verified', 'is_active', 'is_staff', 'date_joined')
    search_fields = ('email', 'first_name', 'last_name', 'national_id')
    ordering = ('-date_joined',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'phone', 'date_of_birth')}),
        (_('Identification'), {'fields': ('national_id', 'kra_pin')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
        (_('User type'), {'fields': ('user_type', 'is_verified')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'password1', 'password2'),
        }),
    )
    
    readonly_fields = ('date_joined', 'last_login')


@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    """Client profile admin"""
    list_display = ('user', 'employment_status', 'monthly_income', 'kyc_verified', 'city', 'county')
    list_filter = ('employment_status', 'kyc_verified', 'county')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'city', 'county')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (_('User'), {'fields': ('user',)}),
        (_('Employment'), {
            'fields': ('employment_status', 'employer_name', 'employer_address', 'monthly_income')
        }),
        (_('Address'), {
            'fields': ('residential_address', 'postal_address', 'city', 'county')
        }),
        (_('Banking'), {
            'fields': ('bank_name', 'bank_account_number', 'bank_branch', 'mpesa_phone')
        }),
        (_('Verification'), {'fields': ('kyc_verified', 'kyc_verified_date', 'kyc_verified_by')}),
        (_('Preferences'), {
            'fields': ('email_notifications', 'sms_notifications', 'preferred_language')
        }),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )
    
    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj and obj.kyc_verified:
            readonly.extend(['kyc_verified_date', 'kyc_verified_by'])
        return readonly


@admin.register(UserDocument)
class UserDocumentAdmin(admin.ModelAdmin):
    """User document admin"""
    list_display = ('user', 'document_type', 'filename', 'is_verified', 'uploaded_at', 'expiry_date')
    list_filter = ('document_type', 'is_verified', 'uploaded_at')
    search_fields = ('user__email', 'filename')
    readonly_fields = ('uploaded_at', 'file_size', 'mime_type')
    date_hierarchy = 'uploaded_at'
    
    fieldsets = (
        (_('User'), {'fields': ('user',)}),
        (_('Document'), {
            'fields': ('document_type', 'file', 'filename', 'file_size', 'mime_type')
        }),
        (_('Verification'), {
            'fields': ('is_verified', 'verified_at', 'verified_by', 'verification_notes')
        }),
        (_('Expiry'), {'fields': ('expiry_date',)}),
        (_('Timestamps'), {'fields': ('uploaded_at', 'updated_at')}),
    )
    
    actions = ['verify_documents', 'unverify_documents']
    
    def verify_documents(self, request, queryset):
        """Bulk verify documents"""
        count = queryset.update(is_verified=True)
        self.message_user(request, f'{count} documents verified successfully.')
    verify_documents.short_description = 'Verify selected documents'
    
    def unverify_documents(self, request, queryset):
        """Bulk unverify documents"""
        count = queryset.update(is_verified=False)
        self.message_user(request, f'{count} documents unverified successfully.')
    unverify_documents.short_description = 'Unverify selected documents'


@admin.register(VerificationRequest)
class VerificationRequestAdmin(admin.ModelAdmin):
    """Verification request admin"""
    list_display = ('user', 'request_type', 'status', 'submitted_at', 'reviewed_at', 'reviewed_by')
    list_filter = ('request_type', 'status', 'submitted_at', 'reviewed_at')
    search_fields = ('user__email', 'notes')
    readonly_fields = ('submitted_at',)
    date_hierarchy = 'submitted_at'
    
    fieldsets = (
        (_('User'), {'fields': ('user',)}),
        (_('Request'), {'fields': ('request_type', 'status', 'notes')}),
        (_('Review'), {
            'fields': ('reviewed_at', 'reviewed_by', 'rejection_reason')
        }),
        (_('Timestamps'), {'fields': ('submitted_at',)}),
    )
    
    actions = ['approve_requests', 'reject_requests']
    
    def approve_requests(self, request, queryset):
        """Bulk approve verification requests"""
        count = queryset.update(
            status=VerificationRequest.Status.APPROVED,
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f'{count} verification requests approved successfully.')
    approve_requests.short_description = 'Approve selected requests'
    
    def reject_requests(self, request, queryset):
        """Bulk reject verification requests"""
        count = queryset.update(
            status=VerificationRequest.Status.REJECTED,
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f'{count} verification requests rejected successfully.')
    reject_requests.short_description = 'Reject selected requests'
