# -*- coding: utf-8 -*-
"""
URL configuration for loans app
"""
from django.urls import path
from . import views
from . import modern_views

app_name = 'loans'

urlpatterns = [
    # Modern loan application
    path('apply/', modern_views.ModernLoanApplicationView.as_view(), name='modern_application'),
    path('application/success/', modern_views.ApplicationSuccessView.as_view(), name='application_success'),
    
    # Loan application wizard (legacy)
    path('wizard/', views.loan_application_wizard, name='application_wizard'),
    
    # Loan application views
    path('applications/', views.LoanApplicationListView.as_view(), name='application_list'),
    path('applications/<uuid:pk>/', views.LoanApplicationDetailView.as_view(), name='application_detail'),
    
    # Document management
    path('applications/<uuid:application_id>/documents/upload/', 
         views.upload_document_view, name='upload_document'),
    path('applications/<uuid:application_id>/documents/<int:document_id>/delete/', 
         views.delete_document_view, name='delete_document'),
    
    # Collateral management
    path('applications/<uuid:application_id>/collateral/add/', 
         views.add_collateral_view, name='add_collateral'),
    path('applications/<uuid:application_id>/collateral/<int:collateral_id>/delete/', 
         views.delete_collateral_view, name='delete_collateral'),
    
    # Guarantor management
    path('applications/<uuid:application_id>/guarantor/add/', 
         views.add_guarantor_view, name='add_guarantor'),
    path('applications/<uuid:application_id>/guarantor/<int:guarantor_id>/delete/', 
         views.delete_guarantor_view, name='delete_guarantor'),
    
    # Repayment schedule
    path('applications/<uuid:application_id>/repayment-schedule/', 
         views.repayment_schedule_view, name='repayment_schedule'),
    
    # Loan agreement
    path('applications/<uuid:application_id>/agreement/', 
         views.download_agreement_view, name='download_agreement'),
    
    # Calculator
    path('calculator/', views.loan_calculator_view, name='calculator'),
    path('calculate/', views.calculate_loan_view, name='calculate'),
]
