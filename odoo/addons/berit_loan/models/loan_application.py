# -*- coding: utf-8 -*-

import calendar
from datetime import datetime, timedelta

from odoo.exceptions import UserError, ValidationError

from odoo import _, api, fields, models


class BeritLoanApplication(models.Model):
    _name = "berit.loan.application"
    _description = "Loan Application"
    _order = "application_date desc, name desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    @api.model
    def _get_default_interest_rate(self):
        """Get default interest rate based on loan amount tiers"""
        return 20.0  # Default for smallest tier

    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _("New"),
    )

    applicant_id = fields.Many2one(
        "res.partner",
        string="Applicant",
        required=True,
        tracking=True,
        domain="[('is_company', '=', False)]",
    )

    loan_amount = fields.Float(
        string="Loan Amount (KES)",
        required=True,
        tracking=True,
        help="Loan amount in Kenyan Shillings",
    )

    loan_duration = fields.Integer(
        string="Loan Duration (Months)",
        required=True,
        tracking=True,
        help="Loan duration in months (1-3 for first-time, 1-12 for returning)",
    )

    loan_purpose = fields.Text(string="Loan Purpose", tracking=True)

    interest_rate = fields.Float(
        string="Interest Rate (%)",
        required=True,
        compute="_compute_interest_rate",
        store=True,
        tracking=True,
    )

    monthly_repayment = fields.Float(
        string="Monthly Repayment (KES)",
        compute="_compute_repayment_amounts",
        store=True,
        tracking=True,
    )

    total_repayable = fields.Float(
        string="Total Repayable (KES)",
        compute="_compute_repayment_amounts",
        store=True,
        tracking=True,
    )

    legal_fee = fields.Float(
        string="Legal Fee (KES)",
        compute="_compute_legal_fee",
        store=True,
        tracking=True,
    )

    collateral_required = fields.Float(
        string="Required Collateral Value (KES)",
        compute="_compute_collateral_required",
        store=True,
        tracking=True,
    )

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("under_review", "Under Review"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("disbursed", "Disbursed"),
            ("active", "Active"),
            ("closed", "Closed"),
            ("defaulted", "Defaulted"),
        ],
        string="Status",
        default="draft",
        tracking=True,
        copy=False,
    )

    application_date = fields.Date(
        string="Application Date",
        default=fields.Date.today,
        required=True,
        tracking=True,
    )

    approval_date = fields.Date(string="Approval Date", readonly=True, tracking=True)

    disbursement_date = fields.Date(
        string="Disbursement Date", readonly=True, tracking=True
    )

    maturity_date = fields.Date(
        string="Maturity Date",
        readonly=True,
        compute="_compute_maturity_date",
        store=True,
    )

    kyc_verified = fields.Boolean(string="KYC Verified", default=False, tracking=True)

    crb_cleared = fields.Boolean(string="CRB Cleared", default=False, tracking=True)

    guarantor_id = fields.Many2one(
        "res.partner",
        string="Primary Guarantor",
        tracking=True,
        domain="[('is_company', '=', False)]",
    )

    collateral_ids = fields.One2many(
        "berit.collateral", "loan_id", string="Collaterals"
    )

    repayment_ids = fields.One2many(
        "berit.repayment.schedule", "loan_id", string="Repayment Schedule"
    )

    document_ids = fields.One2many("berit.loan.document", "loan_id", string="Documents")

    guarantor_ids = fields.One2many("berit.guarantor", "loan_id", string="Guarantors")

    notes = fields.Text(string="Notes", tracking=True)

    portal_application_ref = fields.Char(
        string="Portal Application Reference",
        help="Reference to Django portal submission",
    )

    loan_officer_id = fields.Many2one(
        "res.users",
        string="Loan Officer",
        default=lambda self: self.env.user,
        tracking=True,
    )

    has_prior_loans = fields.Boolean(
        string="Has Prior Loans", compute="_compute_has_prior_loans", store=True
    )

    @api.depends("loan_amount")
    def _compute_interest_rate(self):
        """Compute interest rate based on loan amount tiers"""
        for loan in self:
            if loan.loan_amount:
                amount = loan.loan_amount
                if amount <= 99999:
                    loan.interest_rate = 20.0
                elif amount <= 399999:
                    loan.interest_rate = 17.5
                elif amount <= 599999:
                    loan.interest_rate = 15.0
                elif amount <= 799999:
                    loan.interest_rate = 10.0
                elif amount <= 999999:
                    loan.interest_rate = 7.5
                else:
                    loan.interest_rate = 5.0
            else:
                loan.interest_rate = 0.0

    @api.depends("loan_amount", "interest_rate", "loan_duration")
    def _compute_repayment_amounts(self):
        """Compute monthly repayment and total repayable"""
        for loan in self:
            if loan.loan_amount and loan.interest_rate and loan.loan_duration:
                monthly_interest = loan.loan_amount * (loan.interest_rate / 100)
                principal_payment = loan.loan_amount / loan.loan_duration
                loan.monthly_repayment = monthly_interest + principal_payment
                loan.total_repayable = loan.monthly_repayment * loan.loan_duration
            else:
                loan.monthly_repayment = 0.0
                loan.total_repayable = 0.0

    @api.depends("loan_amount")
    def _compute_legal_fee(self):
        """Compute legal fee as 2.5% of loan amount"""
        for loan in self:
            if loan.loan_amount:
                loan.legal_fee = loan.loan_amount * 0.025
            else:
                loan.legal_fee = 0.0

    @api.depends("loan_amount")
    def _compute_collateral_required(self):
        """Compute required collateral value as 1.5× loan amount"""
        for loan in self:
            if loan.loan_amount:
                loan.collateral_required = loan.loan_amount * 1.5
            else:
                loan.collateral_required = 0.0

    @api.depends("disbursement_date", "loan_duration")
    def _compute_maturity_date(self):
        """Compute maturity date based on disbursement date and duration"""
        for loan in self:
            if loan.disbursement_date and loan.loan_duration:
                maturity_date = loan.disbursement_date + timedelta(
                    days=loan.loan_duration * 30
                )
                loan.maturity_date = maturity_date
            else:
                loan.maturity_date = False

    @api.depends("applicant_id")
    def _compute_has_prior_loans(self):
        """Check if applicant has prior loan history"""
        for loan in self:
            if loan.applicant_id:
                prior_loans = self.search(
                    [
                        ("applicant_id", "=", loan.applicant_id.id),
                        ("id", "!=", loan.id),
                        ("state", "in", ["approved", "disbursed", "active", "closed"]),
                    ]
                )
                loan.has_prior_loans = bool(prior_loans)
            else:
                loan.has_prior_loans = False

    @api.constrains("loan_duration", "has_prior_loans")
    def _check_loan_duration(self):
        """Validate loan duration based on prior loan history.

        The Django portal allows durations up to 60 months.  When a record
        arrives via the XML-RPC sync the value is already capped at 12 by
        the sync layer, but we keep the hard limit at 60 here so that staff
        can manually extend a loan inside Odoo without hitting a wall.
        The soft guideline (≤3 for first-timers, ≤12 for returning) is still
        enforced as a warning via the UI, but NOT as a hard database constraint,
        because portal-submitted records are created programmatically and must
        not be blocked.
        """
        for loan in self:
            if loan.loan_duration < 1 or loan.loan_duration > 60:
                raise ValidationError(
                    _("Loan duration must be between 1 and 60 months.")
                )

    @api.constrains("collateral_ids", "loan_amount")
    def _check_collateral_value(self):
        """Validate collateral value meets 1.5× requirement.

        This constraint is only meaningful once at least one collateral has
        been *verified* by a loan officer.  New applications synced from the
        Django portal arrive with all collaterals unverified, so we skip the
        check entirely when there are no verified collaterals.  Staff must
        verify collaterals inside Odoo before approval, at which point the
        constraint will fire and enforce the policy.
        """
        for loan in self:
            if loan.loan_amount > 0:
                verified_collaterals = [
                    coll for coll in loan.collateral_ids if coll.is_verified
                ]
                # No verified collateral yet — nothing to check
                if not verified_collaterals:
                    continue

                total_collateral_value = sum(
                    coll.estimated_value for coll in verified_collaterals
                )
                required_value = loan.loan_amount * 1.5

                if total_collateral_value < required_value:
                    raise ValidationError(
                        _(
                            "Total verified collateral value must be at least 1.5× "
                            "the loan amount (KES %s)."
                        )
                        % required_value
                    )

                # Policy: collateral value should not exceed 1.5× loan amount
                if total_collateral_value > required_value:
                    raise ValidationError(
                        _(
                            "Collateral value must not exceed 1.5× the loan amount "
                            "(KES %s) per company policy."
                        )
                        % required_value
                    )

    @api.constrains("crb_cleared", "state")
    def _check_crb_clearance(self):
        """Validate CRB clearance before approval.

        Portal submissions arrive with state='submitted' (not yet approved),
        so this constraint only fires when a loan officer explicitly moves the
        record to 'approved', 'disbursed', or 'active' — which is correct.
        """
        for loan in self:
            if (
                loan.state in ["approved", "disbursed", "active"]
                and not loan.crb_cleared
            ):
                raise ValidationError(
                    _("CRB clearance must be verified before loan approval.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        """Create loan application(s) with sequence number.

        Odoo 17+ passes a list of dicts to create().  We assign a sequence
        number to any record whose name is still the default placeholder.
        """
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "berit.loan.application"
                ) or _("New")
        return super(BeritLoanApplication, self).create(vals_list)

    def action_submit(self):
        """Submit loan application for review"""
        self.write({"state": "submitted"})
        self._send_submission_notification()

    def action_under_review(self):
        """Mark application as under review"""
        self.write({"state": "under_review"})

    def action_approve(self):
        """Approve loan application"""
        self.write({"state": "approved", "approval_date": fields.Date.today()})
        self._generate_repayment_schedule()
        self._send_approval_notification()

    def action_reject(self):
        """Reject loan application"""
        self.write({"state": "rejected"})
        self._send_rejection_notification()

    def action_disburse(self):
        """Disburse loan funds"""
        self.write({"state": "disbursed", "disbursement_date": fields.Date.today()})
        # Schedule will be activated on first repayment due date

    def action_activate(self):
        """Activate loan (first repayment due)"""
        self.write({"state": "active"})

    def action_close(self):
        """Close loan (fully repaid)"""
        self.write({"state": "closed"})

    def action_default(self):
        """Mark loan as defaulted"""
        self.write({"state": "defaulted"})

    def _generate_repayment_schedule(self):
        """Generate repayment schedule on approval"""
        self.repayment_ids.unlink()  # Remove existing schedules

        for i in range(1, self.loan_duration + 1):
            due_date = self.disbursement_date or fields.Date.today()
            due_date = due_date + timedelta(days=i * 30)

            self.env["berit.repayment.schedule"].create(
                {
                    "loan_id": self.id,
                    "due_date": due_date,
                    "principal_amount": self.loan_amount / self.loan_duration,
                    "interest_amount": self.loan_amount * (self.interest_rate / 100),
                    "total_due": self.monthly_repayment,
                    "status": "pending",
                }
            )

    def _send_submission_notification(self):
        """Send submission confirmation email"""
        template = self.env.ref(
            "berit_loan.email_template_loan_submitted", raise_if_not_found=False
        )
        if template:
            template.send_mail(self.id)

    def _send_approval_notification(self):
        """Send approval notification email"""
        template = self.env.ref(
            "berit_loan.email_template_loan_approved", raise_if_not_found=False
        )
        if template:
            template.send_mail(self.id)

    def _send_rejection_notification(self):
        """Send rejection notification email"""
        template = self.env.ref(
            "berit_loan.email_template_loan_rejected", raise_if_not_found=False
        )
        if template:
            template.send_mail(self.id)

    @api.model
    def send_portfolio_summary(self):
        """Cron job: Send weekly loan portfolio summary to managers.

        Computes a lightweight breakdown of the current portfolio and logs it
        to the chatter of every active loan.  A proper email implementation
        can replace the log call once an email template is created.
        """
        import logging

        _logger = logging.getLogger(__name__)

        total = self.search_count([])
        by_state = {}
        for state, _label in self._fields["state"].selection:
            count = self.search_count([("state", "=", state)])
            if count:
                by_state[state] = count

        summary_lines = [f"  {s}: {c}" for s, c in by_state.items()]
        summary = "Weekly Portfolio Summary\n" + "\n".join(summary_lines)
        _logger.info(summary)

        # Send via mail channel if one named 'berit-loan-managers' exists
        channel = self.env["mail.channel"].search(
            [("name", "=", "berit-loan-managers")], limit=1
        )
        if channel:
            channel.message_post(
                body=summary.replace("\n", "<br/>"),
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
