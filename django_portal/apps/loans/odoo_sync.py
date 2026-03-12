# -*- coding: utf-8 -*-
"""
Enhanced Odoo integration for complete loan synchronization
"""

import base64
import logging
import xmlrpc.client

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Document-type mapping: Django value  →  Odoo selection value
# ---------------------------------------------------------------------------
DOCUMENT_TYPE_MAP = {
    # accounts.UserDocument types
    "id_copy": "id",
    "kra_pin": "kra_pin",
    "passport_photo": "id",
    "proof_of_address": "other",
    "bank_statement": "bank_statement",
    "mpesa_statement": "mpesa_statement",
    "payslip": "payslip",
    "business_license": "other",
    "other": "other",
    # loans.LoanDocument types (already Odoo-compatible, kept for safety)
    "id": "id",
    "crb": "crb",
    "guarantor_letter": "guarantor_letter",
    "collateral_proof": "collateral_proof",
    "valuation_report": "valuation_report",
}

# Odoo-valid document types (the full selection list on berit.loan.document)
ODOO_VALID_DOC_TYPES = {
    "id",
    "kra_pin",
    "crb",
    "payslip",
    "bank_statement",
    "mpesa_statement",
    "guarantor_letter",
    "collateral_proof",
    "valuation_report",
    "other",
}


def _map_doc_type(django_type):
    """Return an Odoo-valid document_type string, defaulting to 'other'."""
    if django_type in ODOO_VALID_DOC_TYPES:
        return django_type
    return DOCUMENT_TYPE_MAP.get(django_type, "other")


def _read_file_as_base64(file_field):
    """
    Read a Django FileField / ImageField and return a base64-encoded string
    suitable for Odoo Binary fields.  Returns None if the file cannot be read.
    """
    if not file_field:
        return None
    try:
        file_field.open("rb")
        data = file_field.read()
        file_field.close()
        return base64.b64encode(data).decode("utf-8")
    except Exception as exc:
        logger.warning("Could not read file %s: %s", file_field.name, exc)
        return None


def _safe_str(value, fallback=""):
    """Return str(value) or fallback if value is falsy."""
    if value is None:
        return fallback
    return str(value).strip() or fallback


def _safe_float(value, fallback=0.0):
    """Safely convert Decimal / str / None to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value, fallback=0):
    """Safely convert value to int."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


class EnhancedOdooIntegration:
    """Enhanced integration with comprehensive loan tracking"""

    def __init__(self):
        self.odoo_url = getattr(settings, "ODOO_URL", "http://localhost:8069")
        self.odoo_db = getattr(settings, "ODOO_DB", "berit_odoo")
        self.odoo_username = getattr(settings, "ODOO_USERNAME", "admin")
        self.odoo_password = getattr(settings, "ODOO_PASSWORD", "admin")

        # Initialize XML-RPC clients
        self.common = xmlrpc.client.ServerProxy(f"{self.odoo_url}/xmlrpc/2/common")
        self.models = xmlrpc.client.ServerProxy(f"{self.odoo_url}/xmlrpc/2/object")

        # Authenticate
        self.uid = self.common.authenticate(
            self.odoo_db, self.odoo_username, self.odoo_password, {}
        )
        if not self.uid:
            raise Exception("Failed to authenticate with Odoo")

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def _execute(self, model, method, args, kwargs=None):
        """Thin wrapper around execute_kw for brevity."""
        return self.models.execute_kw(
            self.odoo_db,
            self.uid,
            self.odoo_password,
            model,
            method,
            args,
            kwargs or {},
        )

    # ------------------------------------------------------------------
    # Full sync
    # ------------------------------------------------------------------

    def sync_all_loans(self):
        """Synchronise all pending Django loans to Odoo and pull status back."""
        try:
            from .models import LoanApplication

            sync_results = {"django_to_odoo": 0, "odoo_to_django": 0, "errors": []}

            # ── Django → Odoo ──────────────────────────────────────────
            pending = LoanApplication.objects.filter(
                odoo_application_id__isnull=True
            ).exclude(status__in=["draft"])

            for application in pending:
                try:
                    odoo_id = self.create_loan_application(application)
                    application.odoo_application_id = odoo_id
                    application.save(update_fields=["odoo_application_id"])
                    sync_results["django_to_odoo"] += 1
                    logger.info(
                        "Synced %s to Odoo (ID: %s)",
                        application.reference_number,
                        odoo_id,
                    )
                except Exception as exc:
                    msg = f"Error syncing {application.reference_number}: {exc}"
                    sync_results["errors"].append(msg)
                    logger.error(msg)

            # ── Odoo → Django (status updates only) ───────────────────
            odoo_ids = self._execute(
                "berit.loan.application",
                "search",
                [[["portal_application_ref", "!=", ""]]],
            )

            for odoo_id in odoo_ids:
                try:
                    rows = self._execute(
                        "berit.loan.application",
                        "read",
                        [[odoo_id]],
                        {
                            "fields": [
                                "name",
                                "state",
                                "portal_application_ref",
                                "approval_date",
                                "disbursement_date",
                            ]
                        },
                    )
                    if not rows:
                        continue

                    odoo_app = rows[0]
                    portal_ref = odoo_app.get("portal_application_ref")
                    if not portal_ref:
                        continue

                    django_app = LoanApplication.objects.filter(
                        reference_number=portal_ref
                    ).first()
                    if not django_app:
                        continue

                    new_status = self._map_odoo_status(odoo_app.get("state"))
                    if new_status and django_app.status != new_status:
                        django_app.status = new_status
                        update_fields = ["status"]
                        if odoo_app.get("approval_date") and not django_app.approved_at:
                            django_app.approved_at = timezone.now()
                            update_fields.append("approved_at")
                        if (
                            odoo_app.get("disbursement_date")
                            and not django_app.disbursed_at
                        ):
                            django_app.disbursed_at = timezone.now()
                            update_fields.append("disbursed_at")
                        django_app.save(update_fields=update_fields)
                        sync_results["odoo_to_django"] += 1
                        logger.info(
                            "Updated %s status from Odoo: %s",
                            django_app.reference_number,
                            new_status,
                        )

                except Exception as exc:
                    msg = f"Error syncing Odoo loan {odoo_id}: {exc}"
                    sync_results["errors"].append(msg)
                    logger.error(msg)

            return sync_results

        except Exception as exc:
            logger.error("Complete sync error: %s", exc)
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Create loan application (and all children)
    # ------------------------------------------------------------------

    def create_loan_application(self, loan_application):
        """Create a loan application in Odoo with all related records."""
        try:
            partner_id = self._get_or_create_partner(loan_application.user)

            # NOTE: interest_rate, monthly_repayment, total_repayable,
            # legal_fee and collateral_required are *computed+stored* fields
            # in Odoo — Odoo recalculates them from loan_amount, so we do NOT
            # pass them here (they would be silently ignored and then
            # overwritten by the compute method, causing confusion).
            application_data = {
                "name": _safe_str(loan_application.reference_number, "New"),
                "applicant_id": partner_id,
                "loan_amount": _safe_float(loan_application.loan_amount),
                "loan_duration": _safe_int(loan_application.loan_duration, 1),
                "loan_purpose": _safe_str(loan_application.loan_purpose),
                "state": self._map_django_status_to_odoo(loan_application.status),
                "application_date": loan_application.created_at.strftime("%Y-%m-%d"),
                "portal_application_ref": _safe_str(loan_application.reference_number),
                "kyc_verified": bool(loan_application.kyc_verified),
                "crb_cleared": bool(loan_application.crb_cleared),
                "notes": _safe_str(loan_application.notes),
            }

            odoo_id = self._execute(
                "berit.loan.application", "create", [application_data]
            )

            # Create related records — each in its own try/except so a
            # failure in one does not roll back the whole application.
            self._create_documents(loan_application, odoo_id)
            self._create_collaterals(loan_application, odoo_id)
            self._create_guarantors(loan_application, odoo_id)

            if loan_application.status in ["approved", "disbursed", "active"]:
                self._create_repayment_schedule(loan_application, odoo_id)

            return odoo_id

        except Exception as exc:
            raise Exception(f"Error creating loan application in Odoo: {exc}") from exc

    # ------------------------------------------------------------------
    # Repayment schedule
    # ------------------------------------------------------------------

    def _create_repayment_schedule(self, loan_application, odoo_application_id):
        """Create repayment schedule entries in Odoo."""
        try:
            from .utils import LoanCalculator

            calculator = LoanCalculator()
            start_date = (
                loan_application.disbursed_at.date()
                if loan_application.disbursed_at
                else None
            )
            schedule = calculator.generate_amortization_schedule(
                loan_application.loan_amount,
                loan_application.interest_rate,
                loan_application.loan_duration,
                start_date,
            )

            for installment in schedule:
                repayment_data = {
                    "loan_id": odoo_application_id,
                    "installment_number": installment["installment_number"],
                    "due_date": installment["due_date"].strftime("%Y-%m-%d"),
                    "principal_amount": _safe_float(installment["principal_amount"]),
                    "interest_amount": _safe_float(installment["interest_amount"]),
                    "total_due": _safe_float(installment["total_due"]),
                    "amount_paid": 0.0,
                    "state": "pending",
                }
                self._execute("berit.repayment.schedule", "create", [repayment_data])

        except Exception as exc:
            logger.error("Error creating repayment schedule: %s", exc)

    # ------------------------------------------------------------------
    # Status mapping helpers
    # ------------------------------------------------------------------

    def _map_django_status_to_odoo(self, django_status):
        """Map Django loan status to Odoo state value."""
        mapping = {
            "draft": "draft",
            "submitted": "submitted",
            "under_review": "under_review",
            "approved": "approved",
            "rejected": "rejected",
            "disbursed": "disbursed",
            "active": "active",
            "closed": "closed",
            "defaulted": "defaulted",
        }
        return mapping.get(django_status, "draft")

    def _map_odoo_status(self, odoo_status):
        """Map Odoo state value back to Django status string."""
        from .models import LoanApplication

        mapping = {
            "draft": LoanApplication.Status.DRAFT,
            "submitted": LoanApplication.Status.SUBMITTED,
            "under_review": LoanApplication.Status.UNDER_REVIEW,
            "approved": LoanApplication.Status.APPROVED,
            "rejected": LoanApplication.Status.REJECTED,
            "disbursed": LoanApplication.Status.DISBURSED,
            "active": LoanApplication.Status.ACTIVE,
            "closed": LoanApplication.Status.CLOSED,
            "defaulted": LoanApplication.Status.DEFAULTED,
        }
        return mapping.get(odoo_status)

    # ------------------------------------------------------------------
    # Partner (applicant)
    # ------------------------------------------------------------------

    def _get_or_create_partner(self, user):
        """
        Return the Odoo res.partner id for a Django user.
        Searches by email first; creates a new partner if not found.
        Falls back gracefully when first_name / last_name are blank.
        """
        # Search by email (most reliable unique key)
        partners = self._execute(
            "res.partner",
            "search",
            [[["email", "=", user.email]]],
        )
        if partners:
            return partners[0]

        # Build the best name we can
        full_name = _safe_str(getattr(user, "full_name", None))
        if not full_name:
            first = _safe_str(getattr(user, "first_name", ""))
            last = _safe_str(getattr(user, "last_name", ""))
            full_name = f"{first} {last}".strip()
        if not full_name:
            # Last resort: use the part of the email before '@'
            full_name = user.email.split("@")[0]

        phone = ""
        if getattr(user, "phone", None):
            phone = str(user.phone).strip()

        partner_data = {
            "name": full_name,
            "email": user.email,
            "phone": phone,
            "is_company": False,
            "customer_rank": 1,
        }
        return self._execute("res.partner", "create", [partner_data])

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    def _create_documents(self, loan_application, odoo_application_id):
        """
        Sync loan documents to Odoo.

        The Odoo model requires both `file` (Binary) and `filename` (Char).
        Documents whose files cannot be read are skipped with a warning so
        the rest of the sync continues.
        """
        for document in loan_application.documents.all():
            try:
                # Try to get the actual file field (LoanDocument has `file`)
                file_field = getattr(document, "file", None)
                file_b64 = _read_file_as_base64(file_field) if file_field else None

                if not file_b64:
                    logger.warning(
                        "Skipping document %s for loan %s — no readable file content.",
                        document.pk,
                        loan_application.reference_number,
                    )
                    continue

                odoo_doc_type = _map_doc_type(
                    getattr(document, "document_type", "other")
                )

                # Prefer the stored filename; fall back to the file's name attr
                filename = _safe_str(getattr(document, "filename", None))
                if not filename and file_field:
                    filename = (
                        file_field.name.split("/")[-1]
                        if file_field.name
                        else "document"
                    )
                if not filename:
                    filename = f"{odoo_doc_type}_{document.pk}"

                uploaded_at = getattr(document, "uploaded_at", None)
                upload_date = uploaded_at.strftime("%Y-%m-%d") if uploaded_at else None

                document_data = {
                    "loan_id": odoo_application_id,
                    "document_type": odoo_doc_type,
                    "file": file_b64,
                    "filename": filename,
                    "verified": bool(getattr(document, "is_verified", False)),
                    "notes": "",
                }
                if upload_date:
                    document_data["upload_date"] = upload_date

                self._execute("berit.loan.document", "create", [document_data])

            except Exception as exc:
                logger.error("Error syncing document %s: %s", document.pk, exc)

    # ------------------------------------------------------------------
    # Collaterals
    # ------------------------------------------------------------------

    def _create_collaterals(self, loan_application, odoo_application_id):
        """Sync collateral records to Odoo."""
        for collateral in loan_application.collaterals.all():
            try:
                # valuation_date is required in Odoo — default to today if missing
                val_date = getattr(collateral, "valuation_date", None)
                if val_date:
                    valuation_date_str = val_date.strftime("%Y-%m-%d")
                else:
                    from django.utils.timezone import now

                    valuation_date_str = now().date().strftime("%Y-%m-%d")
                    logger.warning(
                        "Collateral %s has no valuation_date; defaulting to today.",
                        collateral.pk,
                    )

                collateral_data = {
                    "loan_id": odoo_application_id,
                    "collateral_type": _safe_str(
                        getattr(collateral, "collateral_type", "other"), "other"
                    ),
                    "description": _safe_str(
                        getattr(collateral, "description", ""), "No description"
                    ),
                    "estimated_value": _safe_float(
                        getattr(collateral, "estimated_value", 0)
                    ),
                    "valuation_date": valuation_date_str,
                    "location": _safe_str(getattr(collateral, "location", "")),
                    "serial_number": _safe_str(
                        getattr(collateral, "serial_number", "")
                    ),
                    "registration_number": _safe_str(
                        getattr(collateral, "registration_number", "")
                    ),
                    "insurance_policy": _safe_str(
                        getattr(collateral, "insurance_policy", "")
                    ),
                    "is_verified": bool(getattr(collateral, "is_verified", False)),
                    "notes": _safe_str(getattr(collateral, "verification_notes", "")),
                }

                self._execute("berit.collateral", "create", [collateral_data])

            except Exception as exc:
                logger.error("Error syncing collateral %s: %s", collateral.pk, exc)

    # ------------------------------------------------------------------
    # Guarantors
    # ------------------------------------------------------------------

    def _create_guarantors(self, loan_application, odoo_application_id):
        """Sync guarantor records to Odoo."""
        for guarantor in loan_application.guarantors.all():
            try:
                guarantor_partner_id = self._get_or_create_guarantor_partner(guarantor)

                guarantor_data = {
                    "loan_id": odoo_application_id,
                    "partner_id": guarantor_partner_id,
                    "name": _safe_str(getattr(guarantor, "name", ""), "Unknown"),
                    "id_number": _safe_str(
                        getattr(guarantor, "id_number", ""), "00000000"
                    ),
                    "phone": _safe_str(getattr(guarantor, "phone", ""), ""),
                    "email": _safe_str(getattr(guarantor, "email", "")),
                    "employer_address": _safe_str(
                        getattr(guarantor, "employer_address", ""), "Not provided"
                    ),
                    "relationship_to_applicant": _safe_str(
                        getattr(guarantor, "relationship_to_applicant", "other"),
                        "other",
                    ),
                    "occupation": _safe_str(getattr(guarantor, "occupation", "")),
                    "monthly_income": _safe_float(
                        getattr(guarantor, "monthly_income", 0)
                    ),
                    "years_known": _safe_int(getattr(guarantor, "years_known", 0)),
                    "is_verified": bool(getattr(guarantor, "is_verified", False)),
                    "notes": _safe_str(getattr(guarantor, "verification_notes", "")),
                }

                self._execute("berit.guarantor", "create", [guarantor_data])

            except Exception as exc:
                logger.error("Error syncing guarantor %s: %s", guarantor.pk, exc)

    def _get_or_create_guarantor_partner(self, guarantor):
        """
        Return the Odoo res.partner id for a guarantor.
        Searches by phone first, then email; creates if not found.
        """
        phone = _safe_str(getattr(guarantor, "phone", ""))
        email = _safe_str(getattr(guarantor, "email", ""))

        # Search by phone (guarantors often share emails with family)
        if phone:
            partners = self._execute(
                "res.partner",
                "search",
                [[["phone", "=", phone]]],
            )
            if partners:
                return partners[0]

        # Fall back to email search
        if email:
            partners = self._execute(
                "res.partner",
                "search",
                [[["email", "=", email]]],
            )
            if partners:
                return partners[0]

        # Build name with fallback
        name = _safe_str(getattr(guarantor, "name", ""))
        if not name:
            name = phone or email or "Unknown Guarantor"

        partner_data = {
            "name": name,
            "phone": phone,
            "email": email,
            "is_company": False,
            "customer_rank": 0,
            "supplier_rank": 0,
        }
        return self._execute("res.partner", "create", [partner_data])

    # ------------------------------------------------------------------
    # Status update / read
    # ------------------------------------------------------------------

    def update_loan_status(self, odoo_application_id, status):
        """Write a new state value on an Odoo loan application."""
        try:
            self._execute(
                "berit.loan.application",
                "write",
                [[odoo_application_id], {"state": status}],
            )
            return True
        except Exception as exc:
            raise Exception(f"Error updating loan status in Odoo: {exc}") from exc

    def get_loan_status(self, odoo_application_id):
        """Read state + key dates from an Odoo loan application."""
        try:
            rows = self._execute(
                "berit.loan.application",
                "read",
                [[odoo_application_id]],
                {"fields": ["state", "approval_date", "disbursement_date"]},
            )
            return rows[0] if rows else None
        except Exception as exc:
            raise Exception(f"Error getting loan status from Odoo: {exc}") from exc

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    def test_connection(self):
        """Return a dict describing the current connection state."""
        try:
            version = self.common.version()
            models = self._execute(
                "ir.model",
                "search",
                [[["model", "=", "berit.loan.application"]]],
            )
            return {
                "status": "connected",
                "odoo_version": version,
                "loan_model_found": len(models) > 0,
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}
