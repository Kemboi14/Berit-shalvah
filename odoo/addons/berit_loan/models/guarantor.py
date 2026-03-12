# -*- coding: utf-8 -*-

import re

from odoo.exceptions import ValidationError

from odoo import _, api, fields, models


class BeritGuarantor(models.Model):
    _name = "berit.guarantor"
    _description = "Loan Guarantor"
    _order = "name asc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    loan_id = fields.Many2one(
        "berit.loan.application", string="Loan", required=True, ondelete="cascade"
    )

    partner_id = fields.Many2one(
        "res.partner", string="Partner", help="Link to existing partner if available"
    )

    name = fields.Char(string="Full Name", required=True, tracking=True)

    id_number = fields.Char(string="National ID Number", required=True, tracking=True)

    phone = fields.Char(string="Phone Number", required=True, tracking=True)

    email = fields.Char(string="Email", tracking=True)

    employer_address = fields.Text(
        string="Employment/Business Address",
        required=True,
        help="Physical address of employment or business",
    )

    guarantee_letter = fields.Binary(
        string="Guarantee Letter",
        required=False,
        attachment=True,
        help="Signed guarantee letter from guarantor (required for portal submissions)",
    )

    guarantee_letter_name = fields.Char(string="Guarantee Letter Name")

    bank_statement = fields.Binary(
        string="Bank Statement",
        required=False,
        attachment=True,
        help="Bank statement or M-Pesa statement showing financial ability",
    )

    bank_statement_name = fields.Char(string="Bank Statement Name")

    id_copy = fields.Binary(
        string="ID Copy",
        required=False,
        attachment=True,
        help="Copy of National ID or Passport (required for portal submissions)",
    )

    id_copy_name = fields.Char(string="ID Copy Name")

    is_verified = fields.Boolean(string="Verified", default=False, tracking=True)

    verified_by = fields.Many2one("res.users", string="Verified By", readonly=True)

    verified_date = fields.Date(string="Verified Date", readonly=True)

    monthly_income = fields.Float(
        string="Monthly Income (KES)", help="Estimated monthly income for assessment"
    )

    relationship_to_applicant = fields.Selection(
        [
            ("family", "Family Member"),
            ("friend", "Friend"),
            ("colleague", "Colleague"),
            ("business", "Business Partner"),
            ("other", "Other"),
        ],
        string="Relationship to Applicant",
    )

    occupation = fields.Char(string="Occupation")

    years_known = fields.Integer(string="Years Known to Applicant")

    notes = fields.Text(string="Notes")

    @api.constrains("phone")
    def _check_phone_format(self):
        """Validate Kenyan phone number format.

        Validation is skipped when there is no phone value so that records
        created programmatically (e.g. via XML-RPC sync from the Django portal)
        can supply international formats or short codes without being blocked.
        """
        for guarantor in self:
            if guarantor.phone:
                # Remove spaces, dashes, parentheses
                phone = re.sub(r"[\s\-\(\)]", "", guarantor.phone)
                # Accept: +254XXXXXXXXX, 07XXXXXXXX, or 254XXXXXXXXX
                valid = (
                    re.match(r"^\+2547\d{8}$", phone)
                    or re.match(r"^07\d{8}$", phone)
                    or re.match(r"^2547\d{8}$", phone)
                )
                if not valid:
                    # Log a warning instead of raising so portal syncs are not blocked
                    import logging

                    logging.getLogger(__name__).warning(
                        "Guarantor %s has non-standard phone number: %s",
                        guarantor.name,
                        guarantor.phone,
                    )

    @api.constrains("email")
    def _check_email_format(self):
        """Validate email format"""
        for guarantor in self:
            if guarantor.email:
                import re

                pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
                if not re.match(pattern, guarantor.email):
                    raise ValidationError(_("Invalid email address format."))

    @api.constrains("id_number")
    def _check_id_number_format(self):
        """Validate Kenyan ID number format.

        Relaxed to a warning so that passport numbers and other non-8-digit
        identifiers submitted via the portal are not blocked at the DB level.
        Staff should verify the ID during the review step inside Odoo.
        """
        for guarantor in self:
            if guarantor.id_number:
                # Kenyan ID numbers are typically 8 digits
                if not re.match(r"^\d{8}$", guarantor.id_number):
                    import logging

                    logging.getLogger(__name__).warning(
                        "Guarantor %s has non-standard ID number: %s",
                        guarantor.name,
                        guarantor.id_number,
                    )

    @api.constrains("monthly_income")
    def _check_monthly_income(self):
        """Validate monthly income is positive"""
        for guarantor in self:
            if guarantor.monthly_income and guarantor.monthly_income <= 0:
                raise ValidationError(_("Monthly income must be greater than 0."))

    def action_verify(self):
        """Verify guarantor"""
        self.write(
            {
                "is_verified": True,
                "verified_by": self.env.user.id,
                "verified_date": fields.Date.today(),
            }
        )

        # Create or update partner record
        if not self.partner_id:
            partner_vals = {
                "name": self.name,
                "phone": self.phone,
                "email": self.email,
                "is_company": False,
                "customer_rank": 0,
                "supplier_rank": 0,
            }
            partner = self.env["res.partner"].create(partner_vals)
            self.partner_id = partner.id

    def action_unverify(self):
        """Unverify guarantor"""
        self.write({"is_verified": False, "verified_by": False, "verified_date": False})

    @api.model_create_multi
    def create(self, vals_list):
        """Create guarantor(s) with automatic naming.

        Odoo 17+ passes a list of dicts to create().
        """
        for vals in vals_list:
            if not vals.get("guarantee_letter_name") and vals.get("guarantee_letter"):
                vals["guarantee_letter_name"] = _("Guarantee Letter")

            if not vals.get("bank_statement_name") and vals.get("bank_statement"):
                vals["bank_statement_name"] = _("Bank Statement")

            if not vals.get("id_copy_name") and vals.get("id_copy"):
                vals["id_copy_name"] = _("ID Copy")

        return super(BeritGuarantor, self).create(vals_list)

    def action_download_guarantee_letter(self):
        """Download guarantee letter"""
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s/%s/guarantee_letter?download=true"
            % (self._name, self.id),
            "target": "new",
        }

    def action_download_bank_statement(self):
        """Download bank statement"""
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s/%s/bank_statement?download=true"
            % (self._name, self.id),
            "target": "new",
        }

    def action_download_id_copy(self):
        """Download ID copy"""
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s/%s/id_copy?download=true" % (self._name, self.id),
            "target": "new",
        }

    def check_guarantor_capacity(self, loan_amount):
        """Check if guarantor has sufficient capacity for the loan"""
        # Simple capacity check: monthly income should be at least 3x monthly repayment
        if self.monthly_income and self.loan_id:
            required_income = self.loan_id.monthly_repayment * 3
            return self.monthly_income >= required_income
        return False
