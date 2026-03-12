# -*- coding: utf-8 -*-
"""
Loan application models for Berit Shalvah Financial Services Portal
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class LoanApplication(models.Model):
    """
    Loan application model
    """

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        SUBMITTED = "submitted", _("Submitted")
        UNDER_REVIEW = "under_review", _("Under Review")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")
        DISBURSED = "disbursed", _("Disbursed")
        ACTIVE = "active", _("Active")
        CLOSED = "closed", _("Closed")
        DEFAULTED = "defaulted", _("Defaulted")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference_number = models.CharField(
        _("Reference Number"), max_length=50, unique=True, editable=False
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="loan_applications",
        verbose_name=_("Applicant"),
    )

    # Loan details
    loan_amount = models.DecimalField(
        _("Loan Amount (KES)"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("1000.00"))],
    )
    loan_duration = models.IntegerField(
        _("Loan Duration (Months)"),
        validators=[MinValueValidator(1), MaxValueValidator(60)],
    )
    loan_purpose = models.TextField(_("Loan Purpose"), blank=True)

    # Employment information
    EMPLOYMENT_TYPE_CHOICES = [
        ("employed", "Employed (Salary)"),
        ("self_employed", "Self-Employed"),
        ("business_owner", "Business Owner"),
        ("student", "Student"),
        ("unemployed", "Unemployed"),
    ]
    employment_type = models.CharField(
        _("Employment Type"),
        max_length=20,
        choices=EMPLOYMENT_TYPE_CHOICES,
        blank=True,
    )
    employment_data = models.JSONField(
        _("Employment Data"),
        default=dict,
        blank=True,
        help_text=_("Employer name, job title, monthly income, duration"),
    )

    # Calculated fields
    interest_rate = models.DecimalField(
        _("Interest Rate (%)"), max_digits=5, decimal_places=2, editable=False
    )
    monthly_repayment = models.DecimalField(
        _("Monthly Repayment (KES)"), max_digits=12, decimal_places=2, editable=False
    )
    total_repayable = models.DecimalField(
        _("Total Repayable (KES)"), max_digits=12, decimal_places=2, editable=False
    )
    legal_fee = models.DecimalField(
        _("Legal Fee (KES)"), max_digits=10, decimal_places=2, editable=False
    )
    collateral_required = models.DecimalField(
        _("Required Collateral Value (KES)"),
        max_digits=12,
        decimal_places=2,
        editable=False,
    )

    # Status and dates
    status = models.CharField(
        _("Status"), max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    submitted_at = models.DateTimeField(_("Submitted At"), null=True, blank=True)
    reviewed_at = models.DateTimeField(_("Reviewed At"), null=True, blank=True)
    approved_at = models.DateTimeField(_("Approved At"), null=True, blank=True)
    disbursed_at = models.DateTimeField(_("Disbursed At"), null=True, blank=True)

    # Verification flags
    kyc_verified = models.BooleanField(_("KYC Verified"), default=False)
    crb_cleared = models.BooleanField(_("CRB Cleared"), default=False)

    # Integration with Odoo
    odoo_application_id = models.IntegerField(
        _("Odoo Application ID"),
        null=True,
        blank=True,
        help_text=_("ID of the corresponding application in Odoo"),
    )
    portal_application_ref = models.CharField(
        _("Portal Application Reference"),
        max_length=100,
        blank=True,
        help_text=_("Reference from Django portal"),
    )

    # Additional information
    notes = models.TextField(_("Notes"), blank=True)
    rejection_reason = models.TextField(_("Rejection Reason"), blank=True)

    class Meta:
        verbose_name = _("Loan Application")
        verbose_name_plural = _("Loan Applications")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference_number} - {self.user.email}"

    def save(self, *args, **kwargs):
        if not self.reference_number:
            self.reference_number = self.generate_reference_number()

        # Calculate loan details before saving
        self.calculate_loan_details()

        super().save(*args, **kwargs)

    def generate_reference_number(self):
        """Generate unique reference number"""
        import datetime

        year = datetime.datetime.now().year
        prefix = f"BERIT/LOAN/{year}/"

        # Get the latest application for this year
        latest = (
            LoanApplication.objects.filter(reference_number__startswith=prefix)
            .order_by("-reference_number")
            .first()
        )

        if latest:
            # Extract the sequence number and increment
            last_seq = int(latest.reference_number.split("/")[-1])
            new_seq = last_seq + 1
        else:
            new_seq = 1

        return f"{prefix}{new_seq:04d}"

    def calculate_loan_details(self):
        """Calculate interest rate, repayments, and fees"""
        if self.loan_amount:
            # Get interest rate based on loan amount
            interest_rates = getattr(settings, "INTEREST_RATES", [])
            for rate_config in interest_rates:
                min_amount = rate_config["min_amount"]
                max_amount = rate_config["max_amount"]

                if max_amount == 0:  # No upper limit
                    if self.loan_amount >= min_amount:
                        self.interest_rate = Decimal(str(rate_config["rate"]))
                        break
                else:
                    if min_amount <= self.loan_amount <= max_amount:
                        self.interest_rate = Decimal(str(rate_config["rate"]))
                        break

            # Calculate monthly repayment and total repayable
            if self.interest_rate and self.loan_duration:
                monthly_interest = self.loan_amount * (self.interest_rate / 100)
                principal_payment = self.loan_amount / self.loan_duration
                self.monthly_repayment = monthly_interest + principal_payment
                self.total_repayable = self.monthly_repayment * self.loan_duration

            # Calculate legal fee (2.5% of loan amount)
            loan_config = getattr(settings, "LOAN_CONFIG", {})
            legal_fee_percentage = loan_config.get("legal_fee_percentage", 2.5)
            self.legal_fee = self.loan_amount * (
                Decimal(str(legal_fee_percentage)) / 100
            )

            # Calculate required collateral value (1.5x loan amount)
            collateral_multiplier = loan_config.get("collateral_multiplier", 1.5)
            self.collateral_required = self.loan_amount * Decimal(
                str(collateral_multiplier)
            )

    def can_submit(self):
        """Check if application can be submitted"""
        required_fields = [
            self.loan_amount,
            self.loan_duration,
            self.interest_rate,
        ]

        return all(required_fields) and self.status == self.Status.DRAFT

    def get_completion_percentage(self):
        """Calculate application completion percentage"""
        completed_steps = 0
        total_steps = 5  # Loan details, KYC, CRB, Collateral, Guarantor

        # Step 1: Loan details
        if self.loan_amount and self.loan_duration and self.loan_purpose:
            completed_steps += 1

        # Step 2: KYC documents
        kyc_docs = self.documents.filter(
            document_type__in=["id_copy", "kra_pin", "passport_photo"]
        )
        if kyc_docs.count() >= 2:
            completed_steps += 1

        # Step 3: CRB clearance
        if self.documents.filter(document_type="crb_clearance").exists():
            completed_steps += 1

        # Step 4: Collateral
        if self.collaterals.exists():
            completed_steps += 1

        # Step 5: Guarantor
        if self.guarantors.exists():
            completed_steps += 1

        return int((completed_steps / total_steps) * 100)


class LoanDocument(models.Model):
    """
    Documents uploaded for loan applications
    """

    class DocumentType(models.TextChoices):
        ID_COPY = "id_copy", _("ID Copy")
        KRA_PIN = "kra_pin", _("KRA PIN Certificate")
        PASSPORT_PHOTO = "passport_photo", _("Passport Photo")
        CRB_CLEARANCE = "crb_clearance", _("CRB Clearance Certificate")
        BANK_STATEMENT = "bank_statement", _("Bank Statement")
        MPESA_STATEMENT = "mpesa_statement", _("M-Pesa Statement")
        PAYSLIP = "payslip", _("Payslip")
        GUARANTOR_LETTER = "guarantor_letter", _("Guarantor Letter")
        COLLATERAL_PROOF = "collateral_proof", _("Collateral Proof of Ownership")
        VALUATION_REPORT = "valuation_report", _("Valuation Report")
        OTHER = "other", _("Other")

    loan_application = models.ForeignKey(
        LoanApplication,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name=_("Loan Application"),
    )
    document_type = models.CharField(
        _("Document Type"), max_length=20, choices=DocumentType.choices
    )
    file = models.FileField(_("File"), upload_to="loan_documents/%Y/%m/")
    filename = models.CharField(_("Filename"), max_length=255)
    file_size = models.PositiveIntegerField(
        _("File Size"), help_text=_("File size in bytes")
    )
    mime_type = models.CharField(_("MIME Type"), max_length=100, blank=True)
    uploaded_at = models.DateTimeField(_("Uploaded At"), auto_now_add=True)

    # Verification
    is_verified = models.BooleanField(_("Verified"), default=False)
    verified_at = models.DateTimeField(_("Verified At"), null=True, blank=True)
    verification_notes = models.TextField(_("Verification Notes"), blank=True)

    # Expiry for documents that expire
    expiry_date = models.DateField(_("Expiry Date"), null=True, blank=True)

    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Loan Document")
        verbose_name_plural = _("Loan Documents")
        ordering = ["-uploaded_at"]
        unique_together = ["loan_application", "document_type"]

    def __str__(self):
        return f"{self.loan_application.reference_number} - {self.get_document_type_display()}"

    def get_file_size_mb(self):
        """Get file size in MB"""
        return round(self.file_size / (1024 * 1024), 2)


class LoanCollateral(models.Model):
    """
    Collateral information for loan applications
    """

    class CollateralType(models.TextChoices):
        PROPERTY = "property", _("Property")
        VEHICLE = "vehicle", _("Vehicle")
        LOGBOOK = "logbook", _("Logbook")
        EQUIPMENT = "equipment", _("Equipment")
        OTHER = "other", _("Other")

    loan_application = models.ForeignKey(
        LoanApplication,
        on_delete=models.CASCADE,
        related_name="collaterals",
        verbose_name=_("Loan Application"),
    )
    collateral_type = models.CharField(
        _("Collateral Type"), max_length=20, choices=CollateralType.choices
    )
    description = models.TextField(_("Description"))
    estimated_value = models.DecimalField(
        _("Estimated Value (KES)"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    valuation_date = models.DateField(_("Valuation Date"))
    location = models.TextField(_("Location/Address"), blank=True)
    serial_number = models.CharField(
        _("Serial/Chassis Number"), max_length=100, blank=True
    )
    registration_number = models.CharField(
        _("Registration Number"), max_length=50, blank=True
    )
    insurance_policy = models.CharField(
        _("Insurance Policy Number"), max_length=100, blank=True
    )

    # Documents
    valuation_document = models.FileField(
        _("Valuation Document"), upload_to="collateral_documents/%Y/%m/", blank=True
    )
    ownership_proof = models.FileField(
        _("Ownership Proof"), upload_to="collateral_documents/%Y/%m/", blank=True
    )

    # Verification
    is_verified = models.BooleanField(_("Verified"), default=False)
    verified_at = models.DateTimeField(_("Verified At"), null=True, blank=True)
    verification_notes = models.TextField(_("Verification Notes"), blank=True)

    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Loan Collateral")
        verbose_name_plural = _("Loan Collaterals")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.loan_application.reference_number} - {self.get_collateral_type_display()}"


class LoanGuarantor(models.Model):
    """
    Guarantor information for loan applications
    """

    class Relationship(models.TextChoices):
        FAMILY = "family", _("Family Member")
        FRIEND = "friend", _("Friend")
        COLLEAGUE = "colleague", _("Colleague")
        BUSINESS = "business", _("Business Partner")
        OTHER = "other", _("Other")

    loan_application = models.ForeignKey(
        LoanApplication,
        on_delete=models.CASCADE,
        related_name="guarantors",
        verbose_name=_("Loan Application"),
    )
    name = models.CharField(_("Full Name"), max_length=200)
    id_number = models.CharField(_("National ID Number"), max_length=20)
    phone = models.CharField(_("Phone Number"), max_length=20)
    email = models.EmailField(_("Email"), blank=True)
    employer_address = models.TextField(_("Employment/Business Address"))
    relationship_to_applicant = models.CharField(
        _("Relationship to Applicant"),
        max_length=20,
        choices=Relationship.choices,
        blank=True,
    )
    occupation = models.CharField(_("Occupation"), max_length=100, blank=True)
    monthly_income = models.DecimalField(
        _("Monthly Income (KES)"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    years_known = models.IntegerField(_("Years Known"), null=True, blank=True)

    # Documents
    guarantee_letter = models.FileField(
        _("Guarantee Letter"), upload_to="guarantor_documents/%Y/%m/"
    )
    bank_statement = models.FileField(
        _("Bank Statement"), upload_to="guarantor_documents/%Y/%m/", blank=True
    )
    id_copy = models.FileField(_("ID Copy"), upload_to="guarantor_documents/%Y/%m/")

    # Verification
    is_verified = models.BooleanField(_("Verified"), default=False)
    verified_at = models.DateTimeField(_("Verified At"), null=True, blank=True)
    verification_notes = models.TextField(_("Verification Notes"), blank=True)

    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Loan Guarantor")
        verbose_name_plural = _("Loan Guarantors")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.loan_application.reference_number} - {self.name}"


class RepaymentSchedule(models.Model):
    """
    Repayment schedule for approved loans
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PAID = "paid", _("Paid")
        OVERDUE = "overdue", _("Overdue")
        PARTIALLY_PAID = "partially_paid", _("Partially Paid")

    loan_application = models.ForeignKey(
        LoanApplication,
        on_delete=models.CASCADE,
        related_name="repayment_schedule",
        verbose_name=_("Loan Application"),
    )
    installment_number = models.IntegerField(_("Installment Number"))
    due_date = models.DateField(_("Due Date"))
    principal_amount = models.DecimalField(
        _("Principal Amount (KES)"), max_digits=12, decimal_places=2
    )
    interest_amount = models.DecimalField(
        _("Interest Amount (KES)"), max_digits=12, decimal_places=2
    )
    total_due = models.DecimalField(
        _("Total Due (KES)"), max_digits=12, decimal_places=2, editable=False
    )
    amount_paid = models.DecimalField(
        _("Amount Paid (KES)"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    payment_date = models.DateField(_("Payment Date"), null=True, blank=True)
    status = models.CharField(
        _("Status"), max_length=20, choices=Status.choices, default=Status.PENDING
    )
    days_overdue = models.IntegerField(_("Days Overdue"), default=0)
    penalty_amount = models.DecimalField(
        _("Penalty Amount (KES)"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    payment_method = models.CharField(
        _("Payment Method"),
        max_length=20,
        choices=[
            ("cash", "Cash"),
            ("bank_transfer", "Bank Transfer"),
            ("mpesa", "M-Pesa"),
            ("cheque", "Cheque"),
            ("other", "Other"),
        ],
        blank=True,
    )
    payment_reference = models.CharField(
        _("Payment Reference"), max_length=100, blank=True
    )
    notes = models.TextField(_("Notes"), blank=True)

    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Repayment Schedule")
        verbose_name_plural = _("Repayment Schedules")
        ordering = ["due_date"]
        unique_together = ["loan_application", "installment_number"]

    def __str__(self):
        return f"{self.loan_application.reference_number} - Installment {self.installment_number}"

    def save(self, *args, **kwargs):
        # Calculate total due
        self.total_due = self.principal_amount + self.interest_amount

        # Calculate penalty if overdue
        if self.status == self.Status.OVERDUE and self.days_overdue > 0:
            self.penalty_amount = self.total_due * (Decimal("0.01") * self.days_overdue)
        else:
            self.penalty_amount = Decimal("0.00")

        super().save(*args, **kwargs)
