# -*- coding: utf-8 -*-
"""
Utility functions for loan management
"""
import xmlrpc.client
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import json


class LoanCalculator:
    """Loan calculator utility class"""
    
    def __init__(self):
        self.interest_rates = getattr(settings, 'INTEREST_RATES', [])
        self.loan_config = getattr(settings, 'LOAN_CONFIG', {})
    
    def calculate(self, loan_amount, loan_duration):
        """Calculate loan details"""
        # Get interest rate
        interest_rate = self.get_interest_rate(loan_amount)
        
        # Calculate monthly repayment
        monthly_interest = loan_amount * (interest_rate / 100)
        principal_payment = loan_amount / loan_duration
        monthly_repayment = monthly_interest + principal_payment
        
        # Calculate total repayable
        total_repayable = monthly_repayment * loan_duration
        
        # Calculate legal fee
        legal_fee_percentage = self.loan_config.get('legal_fee_percentage', 2.5)
        legal_fee = loan_amount * (Decimal(str(legal_fee_percentage)) / 100)
        
        # Calculate required collateral
        collateral_multiplier = self.loan_config.get('collateral_multiplier', 1.5)
        collateral_required = loan_amount * Decimal(str(collateral_multiplier))
        
        return {
            'interest_rate': float(interest_rate),
            'monthly_repayment': float(monthly_repayment),
            'total_repayable': float(total_repayable),
            'legal_fee': float(legal_fee),
            'collateral_required': float(collateral_required),
            'monthly_interest': float(monthly_interest),
            'principal_payment': float(principal_payment),
        }
    
    def get_interest_rate(self, loan_amount):
        """Get interest rate based on loan amount"""
        for rate_config in self.interest_rates:
            min_amount = rate_config['min_amount']
            max_amount = rate_config['max_amount']
            
            if max_amount == 0:  # No upper limit
                if loan_amount >= min_amount:
                    return Decimal(str(rate_config['rate']))
                    break
            else:
                if min_amount <= loan_amount <= max_amount:
                    return Decimal(str(rate_config['rate']))
                    break
        
        # Default rate if no match found
        return Decimal('20.0')
    
    def generate_amortization_schedule(self, loan_amount, interest_rate, loan_duration, start_date=None):
        """Generate loan amortization schedule"""
        if not start_date:
            start_date = timezone.now().date()
        
        schedule = []
        remaining_balance = loan_amount
        monthly_interest_rate = interest_rate / 100
        
        for month in range(1, loan_duration + 1):
            # Calculate due date
            due_date = start_date + timedelta(days=month * 30)
            
            # Calculate interest for this month
            interest_payment = remaining_balance * monthly_interest_rate
            
            # Calculate principal payment
            principal_payment = loan_amount / loan_duration
            
            # Total payment
            total_payment = principal_payment + interest_payment
            
            # Update remaining balance
            remaining_balance -= principal_payment
            
            schedule.append({
                'installment_number': month,
                'due_date': due_date,
                'principal_amount': float(principal_payment),
                'interest_amount': float(interest_payment),
                'total_due': float(total_payment),
                'remaining_balance': float(remaining_balance),
            })
        
        return schedule


class OdooIntegration:
    """Integration with Odoo backend"""
    
    def __init__(self):
        self.odoo_url = getattr(settings, 'ODOO_URL', 'http://localhost:8069')
        self.odoo_db = getattr(settings, 'ODOO_DB', 'berit_odoo')
        self.odoo_username = getattr(settings, 'ODOO_USERNAME', 'admin')
        self.odoo_password = getattr(settings, 'ODOO_PASSWORD', 'admin')
        
        # Initialize XML-RPC client
        self.common = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/common')
        self.models = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/object')
        
        # Authenticate
        self.uid = self.common.authenticate(
            self.odoo_db, 
            self.odoo_username, 
            self.odoo_password, 
            {}
        )
        
        if not self.uid:
            raise Exception("Failed to authenticate with Odoo")
    
    def create_loan_application(self, loan_application):
        """Create loan application in Odoo"""
        try:
            # Get or create partner (applicant)
            partner_id = self._get_or_create_partner(loan_application.user)
            
            # Prepare loan application data
            application_data = {
                'name': loan_application.reference_number,
                'applicant_id': partner_id,
                'loan_amount': float(loan_application.loan_amount),
                'loan_duration': loan_application.loan_duration,
                'loan_purpose': loan_application.loan_purpose or '',
                'interest_rate': float(loan_application.interest_rate),
                'monthly_repayment': float(loan_application.monthly_repayment),
                'total_repayable': float(loan_application.total_repayable),
                'legal_fee': float(loan_application.legal_fee),
                'collateral_required': float(loan_application.collateral_required),
                'state': 'submitted',
                'application_date': loan_application.created_at.strftime('%Y-%m-%d'),
                'portal_application_ref': loan_application.reference_number,
                'kyc_verified': loan_application.kyc_verified,
                'crb_cleared': loan_application.crb_cleared,
                'notes': loan_application.notes or '',
            }
            
            # Create loan application in Odoo
            odoo_application_id = self.models.execute_kw(
                self.odoo_db, self.uid, self.odoo_password,
                'berit.loan.application', 'create',
                [application_data]
            )
            
            # Create documents
            self._create_documents(loan_application, odoo_application_id)
            
            # Create collaterals
            self._create_collaterals(loan_application, odoo_application_id)
            
            # Create guarantors
            self._create_guarantors(loan_application, odoo_application_id)
            
            return odoo_application_id
            
        except Exception as e:
            raise Exception(f"Error creating loan application in Odoo: {str(e)}")
    
    def _get_or_create_partner(self, user):
        """Get or create partner in Odoo"""
        # Search for existing partner by email
        partners = self.models.execute_kw(
            self.odoo_db, self.uid, self.odoo_password,
            'res.partner', 'search',
            [[['email', '=', user.email]]]
        )
        
        if partners:
            return partners[0]
        
        # Create new partner
        partner_data = {
            'name': user.full_name,
            'email': user.email,
            'phone': str(user.phone) if user.phone else '',
            'is_company': False,
            'customer_rank': 1,
        }
        
        partner_id = self.models.execute_kw(
            self.odoo_db, self.uid, self.odoo_password,
            'res.partner', 'create',
            [partner_data]
        )
        
        return partner_id
    
    def _create_documents(self, loan_application, odoo_application_id):
        """Create documents in Odoo"""
        for document in loan_application.documents.all():
            # Note: File attachments would need to be handled separately
            # This is a simplified version
            document_data = {
                'loan_id': odoo_application_id,
                'document_type': document.document_type,
                'filename': document.filename,
                'upload_date': document.uploaded_at.strftime('%Y-%m-%d'),
                'verified': document.is_verified,
                'notes': '',
            }
            
            self.models.execute_kw(
                self.odoo_db, self.uid, self.odoo_password,
                'berit.loan.document', 'create',
                [document_data]
            )
    
    def _create_collaterals(self, loan_application, odoo_application_id):
        """Create collaterals in Odoo"""
        for collateral in loan_application.collaterals.all():
            collateral_data = {
                'loan_id': odoo_application_id,
                'collateral_type': collateral.collateral_type,
                'description': collateral.description,
                'estimated_value': float(collateral.estimated_value),
                'valuation_date': collateral.valuation_date.strftime('%Y-%m-%d'),
                'location': collateral.location or '',
                'is_verified': collateral.is_verified,
                'notes': '',
            }
            
            self.models.execute_kw(
                self.odoo_db, self.uid, self.odoo_password,
                'berit.collateral', 'create',
                [collateral_data]
            )
    
    def _create_guarantors(self, loan_application, odoo_application_id):
        """Create guarantors in Odoo"""
        for guarantor in loan_application.guarantors.all():
            # Create or get guarantor partner
            guarantor_partner_id = self._get_or_create_guarantor_partner(guarantor)
            
            guarantor_data = {
                'loan_id': odoo_application_id,
                'partner_id': guarantor_partner_id,
                'name': guarantor.name,
                'id_number': guarantor.id_number,
                'phone': guarantor.phone,
                'email': guarantor.email or '',
                'employer_address': guarantor.employer_address,
                'relationship_to_applicant': guarantor.relationship_to_applicant or 'other',
                'occupation': guarantor.occupation or '',
                'monthly_income': float(guarantor.monthly_income) if guarantor.monthly_income else 0,
                'years_known': guarantor.years_known or 0,
                'is_verified': guarantor.is_verified,
                'notes': '',
            }
            
            self.models.execute_kw(
                self.odoo_db, self.uid, self.odoo_password,
                'berit.guarantor', 'create',
                [guarantor_data]
            )
    
    def _get_or_create_guarantor_partner(self, guarantor):
        """Get or create guarantor partner in Odoo"""
        # Search for existing partner by phone or ID
        partners = self.models.execute_kw(
            self.odoo_db, self.uid, self.odoo_password,
            'res.partner', 'search',
            [[['phone', '=', guarantor.phone]]]
        )
        
        if partners:
            return partners[0]
        
        # Create new partner
        partner_data = {
            'name': guarantor.name,
            'phone': guarantor.phone,
            'email': guarantor.email or '',
            'is_company': False,
            'customer_rank': 0,
            'supplier_rank': 0,
        }
        
        partner_id = self.models.execute_kw(
            self.odoo_db, self.uid, self.odoo_password,
            'res.partner', 'create',
            [partner_data]
        )
        
        return partner_id
    
    def update_loan_status(self, odoo_application_id, status):
        """Update loan status in Odoo"""
        try:
            self.models.execute_kw(
                self.odoo_db, self.uid, self.odoo_password,
                'berit.loan.application', 'write',
                [[odoo_application_id], {'state': status}]
            )
            return True
        except Exception as e:
            raise Exception(f"Error updating loan status in Odoo: {str(e)}")
    
    def get_loan_status(self, odoo_application_id):
        """Get loan status from Odoo"""
        try:
            applications = self.models.execute_kw(
                self.odoo_db, self.uid, self.odoo_password,
                'berit.loan.application', 'read',
                [odoo_application_id],
                {'fields': ['state', 'approval_date', 'disbursement_date']}
            )
            
            if applications:
                return applications[0]
            return None
            
        except Exception as e:
            raise Exception(f"Error getting loan status from Odoo: {str(e)}")


def validate_kenyan_phone(phone):
    """Validate Kenyan phone number format"""
    phone = str(phone).replace(' ', '').replace('-', '')
    
    if phone.startswith('+2547') and len(phone) == 13:
        return True
    elif phone.startswith('07') and len(phone) == 10:
        return True
    else:
        return False


def validate_kenyan_id(national_id):
    """Validate Kenyan National ID format"""
    if not national_id:
        return False
    
    # Kenyan ID should be exactly 8 digits
    return len(str(national_id)) == 8 and str(national_id).isdigit()


def format_currency(amount, currency='KES'):
    """Format currency amount"""
    try:
        amount = Decimal(str(amount))
        return f"{currency} {amount:,.2f}"
    except (ValueError, TypeError):
        return f"{currency} 0.00"


def generate_reference_number(prefix='BERIT', model_name='LOAN'):
    """Generate unique reference number"""
    import datetime
    
    year = datetime.datetime.now().year
    prefix = f"{prefix}/{model_name}/{year}/"
    
    # This would typically query the database to get the latest number
    # For now, return a formatted prefix
    return prefix + "0001"


def calculate_age(date_of_birth):
    """Calculate age from date of birth"""
    today = timezone.now().date()
    age = today.year - date_of_birth.year
    
    # Adjust if birthday hasn't occurred this year yet
    if today.month < date_of_birth.month or \
       (today.month == date_of_birth.month and today.day < date_of_birth.day):
        age -= 1
    
    return age


# Alias for backward compatibility
EnhancedOdooIntegration = OdooIntegration
