# -*- coding: utf-8 -*-

from odoo.exceptions import ValidationError

from odoo import _, api, fields, models


class BeritCollateral(models.Model):
    _name = "berit.collateral"
    _description = "Loan Collateral"
    _order = "valuation_date desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    loan_id = fields.Many2one(
        "berit.loan.application", string="Loan", required=True, ondelete="cascade"
    )

    collateral_type = fields.Selection(
        [
            ("property", "Property"),
            ("vehicle", "Vehicle"),
            ("logbook", "Logbook"),
            ("equipment", "Equipment"),
            ("other", "Other"),
        ],
        string="Collateral Type",
        required=True,
    )

    description = fields.Text(string="Description", required=True)

    estimated_value = fields.Float(
        string="Estimated Value (KES)", required=True, tracking=True
    )

    valuation_date = fields.Date(
        string="Valuation Date", required=True, default=fields.Date.today
    )

    valuation_document = fields.Binary(string="Valuation Document", attachment=True)

    valuation_document_name = fields.Char(string="Valuation Document Name")

    ownership_proof = fields.Binary(string="Ownership Proof", attachment=True)

    ownership_proof_name = fields.Char(string="Ownership Proof Name")

    is_verified = fields.Boolean(string="Verified", default=False, tracking=True)

    verified_by = fields.Many2one("res.users", string="Verified By", readonly=True)

    verified_date = fields.Date(string="Verified Date", readonly=True)

    location = fields.Text(string="Location/Address")

    serial_number = fields.Char(string="Serial/Chassis Number")

    registration_number = fields.Char(string="Registration Number")

    insurance_policy = fields.Char(string="Insurance Policy Number")

    notes = fields.Text(string="Notes")

    @api.constrains("estimated_value")
    def _check_estimated_value(self):
        """Validate estimated value is positive"""
        for collateral in self:
            if collateral.estimated_value <= 0:
                raise ValidationError(_("Estimated value must be greater than 0."))

    def action_verify(self):
        """Verify collateral"""
        self.write(
            {
                "is_verified": True,
                "verified_by": self.env.user.id,
                "verified_date": fields.Date.today(),
            }
        )

    def action_unverify(self):
        """Unverify collateral"""
        self.write({"is_verified": False, "verified_by": False, "verified_date": False})

    @api.model_create_multi
    def create(self, vals_list):
        """Create collateral(s) with automatic naming.

        Odoo 17+ passes a list of dicts to create().
        """
        for vals in vals_list:
            if not vals.get("valuation_document_name") and vals.get(
                "valuation_document"
            ):
                vals["valuation_document_name"] = _("Valuation Document")

            if not vals.get("ownership_proof_name") and vals.get("ownership_proof"):
                vals["ownership_proof_name"] = _("Ownership Proof")

        return super(BeritCollateral, self).create(vals_list)
