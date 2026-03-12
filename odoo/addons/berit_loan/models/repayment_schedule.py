# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

from odoo import _, api, fields, models


class BeritRepaymentSchedule(models.Model):
    _name = "berit.repayment.schedule"
    _description = "Loan Repayment Schedule"
    _order = "due_date asc"

    loan_id = fields.Many2one(
        "berit.loan.application", string="Loan", required=True, ondelete="cascade"
    )

    due_date = fields.Date(string="Due Date", required=True)

    principal_amount = fields.Float(string="Principal Amount (KES)", required=True)

    interest_amount = fields.Float(string="Interest Amount (KES)", required=True)

    total_due = fields.Float(
        string="Total Due (KES)",
        required=True,
        compute="_compute_total_due",
        store=True,
    )

    amount_paid = fields.Float(string="Amount Paid (KES)", default=0.0)

    payment_date = fields.Date(string="Payment Date", readonly=True)

    status = fields.Selection(
        [
            ("pending", "Pending"),
            ("paid", "Paid"),
            ("overdue", "Overdue"),
            ("partially_paid", "Partially Paid"),
        ],
        string="Status",
        default="pending",
        required=True,
    )

    days_overdue = fields.Integer(
        string="Days Overdue", compute="_compute_days_overdue", store=True
    )

    penalty_amount = fields.Float(
        string="Penalty Amount (KES)", compute="_compute_penalty_amount", store=True
    )

    payment_method = fields.Selection(
        [
            ("cash", "Cash"),
            ("bank_transfer", "Bank Transfer"),
            ("mpesa", "M-Pesa"),
            ("cheque", "Cheque"),
            ("other", "Other"),
        ],
        string="Payment Method",
    )

    payment_reference = fields.Char(string="Payment Reference")

    notes = fields.Text(string="Notes")

    @api.depends("principal_amount", "interest_amount")
    def _compute_total_due(self):
        """Compute total due amount"""
        for schedule in self:
            schedule.total_due = schedule.principal_amount + schedule.interest_amount

    @api.depends("due_date", "status", "amount_paid")
    def _compute_days_overdue(self):
        """Compute days overdue"""
        today = fields.Date.today()
        for schedule in self:
            if schedule.status == "pending" and schedule.due_date < today:
                schedule.days_overdue = (today - schedule.due_date).days
            else:
                schedule.days_overdue = 0

    @api.depends("days_overdue", "total_due")
    def _compute_penalty_amount(self):
        """Compute penalty amount for overdue payments"""
        for schedule in self:
            if schedule.days_overdue > 0:
                # Penalty: 1% of total due per day overdue
                schedule.penalty_amount = (
                    schedule.total_due * 0.01 * schedule.days_overdue
                )
            else:
                schedule.penalty_amount = 0.0

    def action_mark_paid(self):
        """Mark repayment as paid"""
        self.write({"status": "paid", "payment_date": fields.Date.today()})
        self._check_loan_completion()

    def action_mark_partially_paid(self, amount_paid):
        """Mark repayment as partially paid"""
        if amount_paid >= self.total_due:
            raise UserError(_("Amount paid exceeds total due amount."))

        self.write(
            {
                "status": "partially_paid",
                "amount_paid": amount_paid,
                "payment_date": fields.Date.today(),
            }
        )

    def action_record_payment(
        self, amount_paid, payment_method=None, payment_reference=None
    ):
        """Record payment with details"""
        if amount_paid >= self.total_due:
            self.write(
                {
                    "status": "paid",
                    "amount_paid": amount_paid,
                    "payment_date": fields.Date.today(),
                    "payment_method": payment_method,
                    "payment_reference": payment_reference,
                }
            )
        else:
            self.action_mark_partially_paid(amount_paid)
            self.write(
                {
                    "payment_method": payment_method,
                    "payment_reference": payment_reference,
                }
            )

        self._check_loan_completion()

    def _check_loan_completion(self):
        """Check if loan is fully repaid"""
        loan = self.loan_id
        all_paid = all(schedule.status == "paid" for schedule in loan.repayment_ids)

        if all_paid and loan.state == "active":
            loan.action_close()

    @api.model
    def mark_overdue_payments(self):
        """Cron job: Mark overdue payments"""
        today = fields.Date.today()
        overdue_schedules = self.search(
            [("status", "=", "pending"), ("due_date", "<", today)]
        )

        overdue_schedules.write({"status": "overdue"})

        # Check for loan default (overdue > 30 days)
        for schedule in overdue_schedules:
            if schedule.days_overdue > 30 and schedule.loan_id.state == "active":
                schedule.loan_id.action_default()

    def send_reminder_email(self):
        """Send payment reminder email"""
        template = self.env.ref(
            "berit_loan.email_template_payment_reminder", raise_if_not_found=False
        )
        if template:
            template.send_mail(self.id)

    def send_due_soon_reminders(self):
        """Called by ir.cron: send reminders for repayments due within the next 7 days."""
        from dateutil.relativedelta import relativedelta

        cutoff = fields.Date.today() + relativedelta(days=7)
        due_soon = self.search(
            [
                ("status", "in", ["pending", "overdue"]),
                ("due_date", "<=", cutoff),
            ]
        )
        due_soon.send_reminder_email()
