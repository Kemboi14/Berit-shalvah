# -*- coding: utf-8 -*-

import base64

from odoo.exceptions import ValidationError

from odoo import _, api, fields, models


class BeritLoanDocument(models.Model):
    _name = "berit.loan.document"
    _description = "Loan Document"
    _order = "upload_date desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    loan_id = fields.Many2one(
        "berit.loan.application", string="Loan", required=True, ondelete="cascade"
    )

    document_type = fields.Selection(
        [
            ("id", "National ID/Passport"),
            ("kra_pin", "KRA PIN Certificate"),
            ("crb", "CRB Clearance Certificate"),
            ("payslip", "Payslip"),
            ("bank_statement", "Bank Statement"),
            ("mpesa_statement", "M-Pesa Statement"),
            ("guarantor_letter", "Guarantor Letter"),
            ("collateral_proof", "Collateral Proof of Ownership"),
            ("valuation_report", "Valuation Report"),
            ("other", "Other"),
        ],
        string="Document Type",
        required=True,
    )

    file = fields.Binary(string="Document File", required=True, attachment=True)

    filename = fields.Char(string="Filename", required=True)

    upload_date = fields.Date(
        string="Upload Date", default=fields.Date.today, required=True
    )

    verified = fields.Boolean(string="Verified", default=False, tracking=True)

    verified_by = fields.Many2one("res.users", string="Verified By", readonly=True)

    verified_date = fields.Date(string="Verified Date", readonly=True)

    file_size = fields.Float(
        string="File Size (MB)", compute="_compute_file_size", store=True
    )

    mime_type = fields.Char(
        string="MIME Type", compute="_compute_mime_type", store=True
    )

    notes = fields.Text(string="Notes")

    expiry_date = fields.Date(
        string="Expiry Date",
        help="For documents with expiry dates (e.g., CRB clearance)",
    )

    is_required = fields.Boolean(
        string="Required Document",
        default=True,
        help="Mark if this document is required for loan approval",
    )

    @api.depends("file")
    def _compute_file_size(self):
        """Compute file size in MB"""
        for doc in self:
            if doc.file:
                # Convert base64 to bytes and calculate size
                file_data = base64.b64decode(doc.file)
                size_mb = len(file_data) / (1024 * 1024)  # Convert to MB
                doc.file_size = round(size_mb, 2)
            else:
                doc.file_size = 0.0

    @api.depends("filename")
    def _compute_mime_type(self):
        """Compute MIME type based on filename"""
        for doc in self:
            if doc.filename:
                extension = (
                    doc.filename.split(".")[-1].lower() if "." in doc.filename else ""
                )
                mime_types = {
                    "pdf": "application/pdf",
                    "jpg": "image/jpeg",
                    "jpeg": "image/jpeg",
                    "png": "image/png",
                    "doc": "application/msword",
                    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "xls": "application/vnd.ms-excel",
                    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                }
                doc.mime_type = mime_types.get(extension, "application/octet-stream")
            else:
                doc.mime_type = "application/octet-stream"

    @api.constrains("file_size")
    def _check_file_size(self):
        """Validate file size (max 20MB)"""
        max_size = 20  # MB
        for doc in self:
            if doc.file_size > max_size:
                raise ValidationError(_("File size cannot exceed %s MB.") % max_size)

    @api.constrains("filename")
    def _check_file_extension(self):
        """Validate file extension"""
        allowed_extensions = ["pdf", "jpg", "jpeg", "png", "doc", "docx", "xls", "xlsx"]
        for doc in self:
            if doc.filename:
                extension = (
                    doc.filename.split(".")[-1].lower() if "." in doc.filename else ""
                )
                if extension not in allowed_extensions:
                    raise ValidationError(
                        _("File type not allowed. Allowed types: %s")
                        % ", ".join(allowed_extensions)
                    )

    def action_verify(self):
        """Verify document"""
        self.write(
            {
                "verified": True,
                "verified_by": self.env.user.id,
                "verified_date": fields.Date.today(),
            }
        )

    def action_unverify(self):
        """Unverify document"""
        self.write({"verified": False, "verified_by": False, "verified_date": False})

    def action_download(self):
        """Download document"""
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s/%s" % (self._name, self.id),
            "target": "new",
        }

    @api.model_create_multi
    def create(self, vals_list):
        """Create document(s) with automatic filename if not provided.

        Odoo 17+ passes a list of dicts to create().
        """
        for vals in vals_list:
            if not vals.get("filename"):
                document_type = dict(self._fields["document_type"].selection).get(
                    vals.get("document_type")
                )
                vals["filename"] = _("%s - %s") % (document_type, fields.Date.today())

        return super(BeritLoanDocument, self).create(vals_list)

    def check_expiry(self):
        """Check if document is expired"""
        if self.expiry_date and self.expiry_date < fields.Date.today():
            return True
        return False

    @api.model
    def check_all_documents_expiry(self):
        """Cron job: Check for expired documents"""
        today = fields.Date.today()
        expired_docs = self.search(
            [
                ("expiry_date", "!=", False),
                ("expiry_date", "<", today),
                ("verified", "=", True),
            ]
        )

        for doc in expired_docs:
            doc.action_unverify()
            # Send notification about expired document
            doc._send_expiry_notification()

    def _send_expiry_notification(self):
        """Send notification about expired document"""
        template = self.env.ref(
            "berit_loan.email_template_document_expired", raise_if_not_found=False
        )
        if template:
            template.send_mail(self.id)
