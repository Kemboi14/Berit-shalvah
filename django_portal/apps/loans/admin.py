# -*- coding: utf-8 -*-
"""
Admin configuration for loan models
"""
from django.contrib import admin
from .models import (
    LoanApplication, 
    LoanDocument, 
    LoanCollateral, 
    LoanGuarantor,
    RepaymentSchedule
)


@admin.register(LoanApplication)
class LoanApplicationAdmin(admin.ModelAdmin):
    """Admin configuration for loan applications"""
    list_display = [
        'reference_number', 'user', 'loan_amount', 'loan_duration', 
        'status', 'created_at', 'submitted_at'
    ]
    list_filter = ['status', 'loan_duration', 'created_at']
    search_fields = ['reference_number', 'user__email', 'user__first_name', 'user__last_name']
    readonly_fields = [
        'reference_number', 'interest_rate', 'monthly_repayment', 
        'total_repayable', 'legal_fee', 'collateral_required',
        'created_at', 'submitted_at'
    ]
    ordering = ['-created_at']
    
    fieldsets = (
        ('Applicant Information', {
            'fields': ('user',)
        }),
        ('Loan Details', {
            'fields': ('loan_amount', 'loan_duration', 'loan_purpose')
        }),
        ('Calculated Fields', {
            'fields': (
                'interest_rate', 'monthly_repayment', 'total_repayable',
                'legal_fee', 'collateral_required'
            ),
            'classes': ('collapse',)
        }),
        ('Status & Dates', {
            'fields': ('status', 'created_at', 'submitted_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_fieldsets(self, request, obj=None):
        """Customize fieldsets based on whether we're adding or editing"""
        if obj is None:  # Adding new object
            return (
                ('Applicant Information', {
                    'fields': ('user',)
                }),
                ('Loan Details', {
                    'fields': ('loan_amount', 'loan_duration', 'loan_purpose')
                }),
            )
        else:  # Editing existing object
            return self.fieldsets
    
    def get_readonly_fields(self, request, obj=None):
        """Make calculated fields readonly"""
        if obj:  # Editing existing object
            return self.readonly_fields
        return ['reference_number']  # Always readonly


@admin.register(LoanDocument)
class LoanDocumentAdmin(admin.ModelAdmin):
    """Admin configuration for loan documents"""
    list_display = [
        'loan_application', 'document_type', 'filename', 
        'file_size', 'is_verified', 'uploaded_at'
    ]
    list_filter = ['document_type', 'is_verified', 'uploaded_at']
    search_fields = [
        'loan_application__reference_number', 'filename', 
        'loan_application__user__email'
    ]
    readonly_fields = ['uploaded_at', 'file_size']
    ordering = ['-uploaded_at']


@admin.register(LoanCollateral)
class LoanCollateralAdmin(admin.ModelAdmin):
    """Admin configuration for loan collateral"""
    list_display = [
        'loan_application', 'collateral_type', 'estimated_value', 
        'valuation_date', 'location'
    ]
    list_filter = ['collateral_type', 'valuation_date']
    search_fields = [
        'loan_application__reference_number', 'description', 'location',
        'loan_application__user__email'
    ]
    ordering = ['-loan_application__created_at']


@admin.register(LoanGuarantor)
class LoanGuarantorAdmin(admin.ModelAdmin):
    """Admin configuration for loan guarantors"""
    list_display = [
        'loan_application', 'name', 'id_number', 'phone', 
        'relationship_to_applicant', 'monthly_income'
    ]
    list_filter = ['relationship_to_applicant']
    search_fields = [
        'loan_application__reference_number', 'name', 'id_number', 'phone',
        'loan_application__user__email'
    ]
    ordering = ['-loan_application__created_at']


@admin.register(RepaymentSchedule)
class RepaymentScheduleAdmin(admin.ModelAdmin):
    """Admin configuration for repayment schedules"""
    list_display = [
        'loan_application', 'installment_number', 'due_date', 
        'total_due', 'amount_paid', 'status'
    ]
    list_filter = ['status', 'due_date']
    search_fields = [
        'loan_application__reference_number',
        'loan_application__user__email'
    ]
    readonly_fields = ['installment_number', 'total_due']
    ordering = ['loan_application', 'installment_number']
    
    def get_readonly_fields(self, request, obj=None):
        """Make calculated fields readonly"""
        if obj:  # Editing existing object
            return self.readonly_fields
        return []
