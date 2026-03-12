# -*- coding: utf-8 -*-
{
    'name': 'Berit Shalvah Loan Management',
    'version': '1.0',
    'category': 'Finance',
    'summary': 'Complete loan management system for Berit Shalvah Financial Services',
    'description': """
Berit Shalvah Loan Management System
====================================

This module provides comprehensive loan management functionality for Berit Shalvah Financial Services Ltd.

Features:
----------
- Loan application management with workflow states
- Automated interest rate calculation based on loan amount tiers
- Collateral management and verification
- Guarantor management
- Document management and verification
- Automated repayment schedule generation
- CRB clearance tracking
- KYC verification
- Loan agreement PDF generation
- Email notifications and reminders
- Role-based access control

Interest Rates (Monthly):
- KES 1 - 99,999: 20%
- KES 100,000 - 399,999: 17.5%
- KES 400,000 - 599,999: 15%
- KES 600,000 - 799,999: 10%
- KES 800,000 - 999,999: 7.5%
- KES 1,000,000+: 5%

Collateral Requirements:
- Minimum collateral value: 1.5× loan amount
- Maximum collateral value: 1.5× loan amount (per policy)

Legal Fee: 2.5% of loan amount (one-time, client-paid)
""",
    'author': 'Berit Shalvah Financial Services Ltd',
    'website': 'https://beritshalvah.co.ke',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'account',
        'web',
        'contacts',
        'portal',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/loan_sequence.xml',
        # 'data/interest_rates.xml',  # Removed - references non-existent model
        'views/loan_application_views.xml',
        'views/repayment_views.xml',
        'views/collateral_views.xml',
        'views/document_views.xml',
        'views/guarantor_views.xml',
        'views/berit_loan_menu.xml',
        'reports/loan_agreement_report.xml',
        'data/ir_cron.xml',
    ],
    'demo': [
        'demo/loan_demo.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
    'sequence': 100,
}
