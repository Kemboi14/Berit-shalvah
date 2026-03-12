# -*- coding: utf-8 -*-
"""
Enhanced forms for modern loan application with KYC requirements
"""
from django import forms
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from django.utils import timezone
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Div, HTML, Submit
from crispy_bootstrap5.bootstrap5 import BS5Accordion
from .models import LoanApplication, LoanDocument, LoanCollateral, LoanGuarantor
import re
from datetime import date


class PersonalInformationForm(forms.Form):
    """Personal information form with Kenyan validation"""
    
    full_name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your full legal name'
        }),
        help_text='Enter your full legal name as appears on your ID'
    )
    
    national_id = forms.CharField(
        max_length=8,
        validators=[
            RegexValidator(r'^\d{8}$', 'National ID must be exactly 8 digits')
        ],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g., 12345678',
            'pattern': '[0-9]{8}',
            'maxlength': '8'
        }),
        help_text='8-digit Kenyan National ID number'
    )
    
    phone = forms.CharField(
        max_length=12,
        validators=[
            RegexValidator(
                r'^(07[0-9]{8}|2547[0-9]{8})$',
                'Enter a valid Kenyan phone number (07XXXXXXXX or 2547XXXXXXXX)'
            )
        ],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g., 0712345678 or 254712345678'
        })
    )
    
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'your.email@example.com'
        })
    )
    
    date_of_birth = forms.DateField(
        validators=[
            MinValueValidator(date(1940, 1, 1)),
            MaxValueValidator(date.today().replace(year=date.today().year - 18))
        ],
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'max': date.today().replace(year=date.today().year - 18).strftime('%Y-%m-%d')
        }),
        help_text='You must be at least 18 years old'
    )
    
    gender = forms.ChoiceField(
        choices=[
            ('', 'Select Gender'),
            ('male', 'Male'),
            ('female', 'Female'),
            ('other', 'Other')
        ],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    address = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Enter your complete residential address'
        })
    )
    
    county = forms.ChoiceField(
        choices=[
            ('', 'Select County'),
            ('nairobi', 'Nairobi'),
            ('mombasa', 'Mombasa'),
            ('kisumu', 'Kisumu'),
            ('nakuru', 'Nakuru'),
            ('eldoret', 'Eldoret'),
            ('thika', 'Thika'),
            ('kitale', 'Kitale'),
            ('garissa', 'Garissa'),
            ('kakamega', 'Kakamega'),
            ('meru', 'Meru'),
            ('nyeri', 'Nyeri'),
            ('kisii', 'Kisii'),
            ('bungoma', 'Bungoma'),
            ('turkana', 'Turkana'),
            ('west_pokot', 'West Pokot'),
            ('samburu', 'Samburu'),
            ('trans_nzoia', 'Trans Nzoia'),
            ('uasin_gishu', 'Uasin Gishu'),
            ('elgeyo_marakwet', 'Elgeyo Marakwet'),
            ('nandi', 'Nandi'),
            ('baringo', 'Baringo'),
            ('laikipia', 'Laikipia'),
            ('nakuru', 'Nakuru'),
            ('narok', 'Narok'),
            ('kajiado', 'Kajiado'),
            ('kiambu', 'Kiambu'),
            ('muranga', "Murang'a"),
            ('kirinyaga', 'Kirinyaga'),
            ('nyandarua', 'Nyandarua'),
            ('nyeri', 'Nyeri'),
            ('embu', 'Embu'),
            ('tharaka_nithi', 'Tharaka Nithi'),
            ('meru', 'Meru'),
            ('isiolo', 'Isiolo'),
            ('marsabit', 'Marsabit'),
            ('wajir', 'Wajir'),
            ('mandera', 'Mandera'),
            ('garissa', 'Garissa'),
            ('tana_river', 'Tana River'),
            ('lamu', 'Lamu'),
            ('taita_taveta', 'Taita Taveta'),
            ('kwale', 'Kwale'),
            ('kilifi', 'Kilifi'),
            ('mombasa', 'Mombasa'),
            ('kwale', 'Kwale'),
            ('tana_river', 'Tana River'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    postal_code = forms.CharField(
        max_length=10,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g., 00100'
        })
    )
    
    marital_status = forms.ChoiceField(
        choices=[
            ('', 'Select Status'),
            ('single', 'Single'),
            ('married', 'Married'),
            ('divorced', 'Divorced'),
            ('widowed', 'Widowed')
        ],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    dependents = forms.IntegerField(
        validators=[
            MinValueValidator(0),
            MaxValueValidator(20)
        ],
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'max': '20'
        })
    )
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Pre-fill with user data if available
        if self.user:
            self.fields['full_name'].initial = self.user.get_full_name()
            self.fields['email'].initial = self.user.email
            if hasattr(self.user, 'phone'):
                self.fields['phone'].initial = self.user.phone


class LoanDetailsForm(forms.Form):
    """Loan details form with validation"""
    
    LOAN_PURPOSE_CHOICES = [
        ('', 'Select Purpose'),
        ('business', 'Business Capital'),
        ('education', 'School Fees'),
        ('medical', 'Medical Emergency'),
        ('home', 'Home Improvement'),
        ('personal', 'Personal Use'),
        ('emergency', 'Emergency'),
        ('agriculture', 'Agriculture'),
        ('construction', 'Construction'),
        ('other', 'Other')
    ]
    
    loan_amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[
            MinValueValidator(1000),
            MaxValueValidator(500000)
        ],
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '1000',
            'max': '500000',
            'step': '1000'
        }),
        help_text='Between KES 1,000 and KES 500,000'
    )
    
    loan_duration = forms.ChoiceField(
        choices=[
            ('', 'Select Duration'),
            (1, '1 Month'),
            (3, '3 Months'),
            (6, '6 Months'),
            (9, '9 Months'),
            (12, '12 Months')
        ],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    loan_purpose_category = forms.ChoiceField(
        choices=LOAN_PURPOSE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    loan_purpose = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Please describe in detail how you intend to use this loan'
        }),
        help_text='Provide a detailed description of your loan purpose'
    )
    
    def clean_loan_amount(self):
        amount = self.cleaned_data.get('loan_amount')
        if amount and amount < 1000:
            raise forms.ValidationError('Minimum loan amount is KES 1,000')
        if amount and amount > 500000:
            raise forms.ValidationError('Maximum loan amount is KES 500,000')
        return amount


class KYCDocumentsForm(forms.Form):
    """KYC documents upload form"""
    
    id_copy = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*,.pdf'
        }),
        help_text='Upload front and back of your National ID'
    )
    
    kra_pin = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf'
        }),
        help_text='Upload your KRA PIN certificate (PDF format)'
    )
    
    passport_photo = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*'
        }),
        help_text='Recent passport-sized photo'
    )
    
    crb_clearance = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,image/*'
        }),
        help_text='CRB clearance certificate (optional but recommended)'
    )
    
    bank_statement = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf'
        }),
        help_text='Last 6 months bank statements (optional but recommended)'
    )
    
    payslip = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,image/*'
        }),
        help_text='Latest payslip (optional but recommended)'
    )
    
    def clean_id_copy(self):
        file = self.cleaned_data.get('id_copy')
        if not file:
            raise forms.ValidationError('Please upload your National ID')
        
        if file.size > 5 * 1024 * 1024:  # 5MB
            raise forms.ValidationError('File size must be less than 5MB')
        
        return file
    
    def clean_kra_pin(self):
        file = self.cleaned_data.get('kra_pin')
        if file and file.size > 5 * 1024 * 1024:
            raise forms.ValidationError('File size must be less than 5MB')
        return file
    
    def clean_passport_photo(self):
        file = self.cleaned_data.get('passport_photo')
        if file and file.size > 5 * 1024 * 1024:
            raise forms.ValidationError('File size must be less than 5MB')
        return file


class CollateralForm(forms.Form):
    """Collateral information form"""
    
    COLLATERAL_TYPES = [
        ('', 'Select Type'),
        ('property', 'Property/Land'),
        ('vehicle', 'Vehicle'),
        ('logbook', 'Logbook'),
        ('equipment', 'Equipment'),
        ('livestock', 'Livestock'),
        ('jewelry', 'Jewelry'),
        ('investments', 'Investments'),
        ('other', 'Other')
    ]
    
    collateral_type = forms.ChoiceField(
        choices=COLLATERAL_TYPES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Describe the collateral in detail'
        })
    )
    
    estimated_value = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'step': '1000'
        })
    )
    
    valuation_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    location = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Where is the collateral located?'
        })
    )
    
    serial_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Vehicle chassis, logbook number, etc.'
        })
    )
    
    registration_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Registration number if applicable'
        })
    )
    
    insurance_policy = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Insurance policy number if applicable'
        })
    )
    
    valuation_document = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,image/*'
        }),
        help_text='Upload valuation report (optional)'
    )
    
    ownership_proof = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,image/*'
        }),
        help_text='Upload proof of ownership (optional)'
    )


class GuarantorForm(forms.Form):
    """Guarantor information form"""
    
    RELATIONSHIP_CHOICES = [
        ('', 'Select Relationship'),
        ('family', 'Family Member'),
        ('friend', 'Friend'),
        ('colleague', 'Colleague'),
        ('business', 'Business Partner'),
        ('neighbor', 'Neighbor'),
        ('other', 'Other')
    ]
    
    name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': "Guarantor's full name"
        })
    )
    
    id_number = forms.CharField(
        max_length=8,
        validators=[
            RegexValidator(r'^\d{8}$', 'National ID must be exactly 8 digits')
        ],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Guarantor National ID',
            'pattern': '[0-9]{8}',
            'maxlength': '8'
        })
    )
    
    phone = forms.CharField(
        max_length=12,
        validators=[
            RegexValidator(
                r'^(07[0-9]{8}|2547[0-9]{8})$',
                'Enter a valid Kenyan phone number'
            )
        ],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Guarantor phone number'
        })
    )
    
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Guarantor email address'
        })
    )
    
    employer_address = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': "Guarantor's work or business address"
        })
    )
    
    relationship_to_applicant = forms.ChoiceField(
        choices=RELATIONSHIP_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    occupation = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g., Teacher, Engineer, Business Owner'
        })
    )
    
    monthly_income = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'step': '1000'
        })
    )
    
    years_known = forms.IntegerField(
        required=False,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(50)
        ],
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'max': '50'
        })
    )
    
    guarantee_letter = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,image/*'
        }),
        help_text='Guarantor letter (optional)'
    )
    
    bank_statement = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf'
        }),
        help_text='Guarantor bank statement (optional)'
    )
    
    id_copy = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*,.pdf'
        }),
        help_text='Guarantor ID copy'
    )


class TermsAndConditionsForm(forms.Form):
    """Terms and conditions acceptance form"""
    
    terms_accepted = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        required=True,
        label='I accept the Terms and Conditions and Privacy Policy'
    )
    
    consent_to_check = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        required=True,
        label='I consent to Berit Shalvah conducting credit checks and verifying my information'
    )
    
    information_true = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        required=True,
        label='I confirm that all information provided is true and accurate'
    )


class ModernLoanApplicationForm(forms.Form):
    """Complete modern loan application form"""
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Initialize sub-forms
        self.personal_form = PersonalInformationForm(user=self.user, *args, **kwargs)
        self.loan_form = LoanDetailsForm(*args, **kwargs)
        self.kyc_form = KYCDocumentsForm(*args, **kwargs)
        self.terms_form = TermsAndConditionsForm(*args, **kwargs)
        
        # Dynamic forms for collateral and guarantors
        self.collateral_forms = []
        self.guarantor_forms = []
    
    def add_collateral_form(self):
        """Add a new collateral form"""
        collateral_form = CollateralForm(prefix=f'collateral_{len(self.collateral_forms)}')
        self.collateral_forms.append(collateral_form)
        return collateral_form
    
    def add_guarantor_form(self):
        """Add a new guarantor form"""
        guarantor_form = GuarantorForm(prefix=f'guarantor_{len(self.guarantor_forms)}')
        self.guarantor_forms.append(guarantor_form)
        return guarantor_form
    
    def is_valid(self):
        """Validate all forms"""
        forms_to_check = [
            self.personal_form,
            self.loan_form,
            self.kyc_form,
            self.terms_form
        ] + self.collateral_forms + self.guarantor_forms
        
        return all(form.is_valid() for form in forms_to_check)
    
    def clean(self):
        """Cross-form validation"""
        cleaned_data = super().clean()
        
        # Validate loan amount vs collateral value
        loan_amount = self.loan_form.cleaned_data.get('loan_amount')
        if loan_amount:
            total_collateral_value = 0
            for form in self.collateral_forms:
                if form.is_valid():
                    total_collateral_value += form.cleaned_data.get('estimated_value', 0)
            
            if total_collateral_value > 0 and total_collateral_value < loan_amount:
                raise forms.ValidationError(
                    'Total collateral value should be at least equal to the loan amount'
                )
        
        return cleaned_data
    
    def save(self, commit=True):
        """Save the loan application"""
        if not self.is_valid():
            raise ValueError('Form is not valid')
        
        # Create loan application
        application = LoanApplication(
            user=self.user,
            loan_amount=self.loan_form.cleaned_data['loan_amount'],
            loan_duration=int(self.loan_form.cleaned_data['loan_duration']),
            loan_purpose=self.loan_form.cleaned_data['loan_purpose'],
            status=LoanApplication.Status.DRAFT
        )
        
        if commit:
            application.save()
            
            # Save collaterals
            for form in self.collateral_forms:
                if form.is_valid():
                    collateral = LoanCollateral(
                        loan_application=application,
                        collateral_type=form.cleaned_data['collateral_type'],
                        description=form.cleaned_data['description'],
                        estimated_value=form.cleaned_data['estimated_value'],
                        valuation_date=form.cleaned_data['valuation_date'],
                        location=form.cleaned_data.get('location', ''),
                        serial_number=form.cleaned_data.get('serial_number', ''),
                        registration_number=form.cleaned_data.get('registration_number', ''),
                        insurance_policy=form.cleaned_data.get('insurance_policy', '')
                    )
                    collateral.save()
            
            # Save guarantors
            for form in self.guarantor_forms:
                if form.is_valid():
                    guarantor = LoanGuarantor(
                        loan_application=application,
                        name=form.cleaned_data['name'],
                        id_number=form.cleaned_data['id_number'],
                        phone=form.cleaned_data['phone'],
                        email=form.cleaned_data.get('email', ''),
                        employer_address=form.cleaned_data['employer_address'],
                        relationship_to_applicant=form.cleaned_data['relationship_to_applicant'],
                        occupation=form.cleaned_data.get('occupation', ''),
                        monthly_income=form.cleaned_data['monthly_income'],
                        years_known=form.cleaned_data.get('years_known')
                    )
                    guarantor.save()
        
        return application


class LoanApplicationStatusForm(forms.ModelForm):
    """Form for updating loan application status"""
    
    class Meta:
        model = LoanApplication
        fields = ['status', 'notes', 'rejection_reason']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'rejection_reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3})
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter status choices based on current status
        current_status = self.instance.status
        status_choices = []
        
        if current_status == LoanApplication.Status.DRAFT:
            status_choices = [
                (LoanApplication.Status.DRAFT, 'Draft'),
                (LoanApplication.Status.SUBMITTED, 'Submitted'),
            ]
        elif current_status == LoanApplication.Status.SUBMITTED:
            status_choices = [
                (LoanApplication.Status.SUBMITTED, 'Submitted'),
                (LoanApplication.Status.UNDER_REVIEW, 'Under Review'),
                (LoanApplication.Status.REJECTED, 'Rejected'),
            ]
        elif current_status == LoanApplication.Status.UNDER_REVIEW:
            status_choices = [
                (LoanApplication.Status.UNDER_REVIEW, 'Under Review'),
                (LoanApplication.Status.APPROVED, 'Approved'),
                (LoanApplication.Status.REJECTED, 'Rejected'),
            ]
        elif current_status == LoanApplication.Status.APPROVED:
            status_choices = [
                (LoanApplication.Status.APPROVED, 'Approved'),
                (LoanApplication.Status.DISBURSED, 'Disbursed'),
            ]
        elif current_status == LoanApplication.Status.DISBURSED:
            status_choices = [
                (LoanApplication.Status.DISBURSED, 'Disbursed'),
                (LoanApplication.Status.ACTIVE, 'Active'),
            ]
        elif current_status == LoanApplication.Status.ACTIVE:
            status_choices = [
                (LoanApplication.Status.ACTIVE, 'Active'),
                (LoanApplication.Status.CLOSED, 'Closed'),
                (LoanApplication.Status.DEFAULTED, 'Defaulted'),
            ]
        
        self.fields['status'].choices = status_choices
        
        # Make rejection_reason required if status is rejected
        if current_status in [LoanApplication.Status.SUBMITTED, LoanApplication.Status.UNDER_REVIEW]:
            self.fields['rejection_reason'].required = False
        else:
            self.fields['rejection_reason'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get('status')
        rejection_reason = cleaned_data.get('rejection_reason')
        
        if status == LoanApplication.Status.REJECTED and not rejection_reason:
            raise forms.ValidationError(
                'Rejection reason is required when rejecting an application'
            )
        
        return cleaned_data
