# -*- coding: utf-8 -*-
"""
Management command: fix_odoo_partner_names
==========================================

Repairs Odoo res.partner records whose name is blank, False, or is still
just the email-prefix / Django username — symptoms of the original sync bug
where get_full_name() returned "" and the fallback was a non-human-readable
value.

For every Django user who has a linked Odoo loan application, the command:
  1. Resolves the best available display name from Django
  2. Looks up the matching res.partner in Odoo by email
  3. Updates the name if it is missing or looks like a placeholder

Usage
-----
# Preview what would change without touching Odoo:
    python manage.py fix_odoo_partner_names --dry-run

# Apply fixes:
    python manage.py fix_odoo_partner_names

# Only fix a specific user by email:
    python manage.py fix_odoo_partner_names --email john@example.com

# Increase verbosity for full detail:
    python manage.py fix_odoo_partner_names --verbosity 2
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

logger = logging.getLogger(__name__)


def _best_name(user):
    """
    Resolve the best display name for a Django user.

    Resolution order (first non-empty value wins):
      1. get_full_name()       – Django AbstractUser built-in
      2. full_name property    – custom property on the User model
      3. first_name + last_name
      4. username
      5. email prefix (everything before @)
    """
    candidates = []

    try:
        candidates.append((user.get_full_name() or "").strip())
    except Exception:
        pass

    try:
        candidates.append((getattr(user, "full_name", None) or "").strip())
    except Exception:
        pass

    first = (getattr(user, "first_name", None) or "").strip()
    last = (getattr(user, "last_name", None) or "").strip()
    if first or last:
        candidates.append(f"{first} {last}".strip())

    candidates.append((getattr(user, "username", None) or "").strip())

    try:
        candidates.append(user.email.split("@")[0].strip())
    except Exception:
        pass

    return next((c for c in candidates if c), "")


def _is_placeholder(name, user):
    """
    Return True if `name` looks like it was never a real human name —
    i.e. it is blank, the email prefix, or the raw username.
    """
    if not name:
        return True
    stripped = name.strip()
    if not stripped:
        return True
    try:
        if stripped == user.email.split("@")[0]:
            return True
    except Exception:
        pass
    username = (getattr(user, "username", None) or "").strip()
    if username and stripped == username:
        return True
    return False


class Command(BaseCommand):
    help = (
        "Fix blank / placeholder applicant names on Odoo res.partner records "
        "that were created by the sync layer before the name-resolution bug was fixed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            default=False,
            help="Show what would be changed without writing anything to Odoo.",
        )
        parser.add_argument(
            "--email",
            dest="email",
            default=None,
            metavar="EMAIL",
            help="Only process the user with this email address.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        email_filter = options["email"]
        verbosity = options["verbosity"]

        # ── Import models here so --help never requires a DB ────────────
        try:
            from apps.accounts.models import User
            from apps.loans.sync.perfect_sync import PerfectOdooSync
        except ImportError as exc:
            raise CommandError(f"Import error: {exc}") from exc

        # ── Connect to Odoo ─────────────────────────────────────────────
        if not dry_run:
            try:
                sync = PerfectOdooSync()
            except Exception as conn_err:
                raise CommandError(
                    f"Could not connect to Odoo: {conn_err}\n\n"
                    "Check ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD in settings/.env"
                )
        else:
            sync = None

        # ── Find users who have at least one synced loan ─────────────────
        qs = User.objects.filter(
            loan_applications__odoo_application_id__isnull=False
        ).distinct()

        if email_filter:
            qs = qs.filter(email=email_filter)
            if not qs.exists():
                raise CommandError(
                    f"No user found with email '{email_filter}' "
                    "that has a synced loan application."
                )

        total = qs.count()
        if total == 0:
            self.stdout.write(
                self.style.WARNING(
                    "No users with synced loan applications found. Nothing to do."
                )
            )
            return

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"{'[DRY RUN] ' if dry_run else ''}"
                f"Checking {total} user(s) with synced Odoo loans…"
            )
        )

        fixed = 0
        already_ok = 0
        skipped = 0
        errors = 0

        for user in qs.order_by("email"):
            name = _best_name(user)

            if verbosity >= 2:
                self.stdout.write(f"  User: {user.email}  →  best name: '{name}'")

            if not name:
                self.stdout.write(
                    self.style.WARNING(
                        f"  SKIP  {user.email} — could not determine a real name."
                    )
                )
                skipped += 1
                continue

            # Look up the partner in Odoo by email
            try:
                if dry_run:
                    # In dry-run mode we can't call Odoo, so just report intent
                    self.stdout.write(
                        self.style.SUCCESS(f"  WOULD FIX  {user.email} → '{name}'")
                    )
                    fixed += 1
                    continue

                existing = sync._execute_rpc(
                    "res.partner",
                    "search_read",
                    [[["email", "=", user.email]]],
                    {"fields": ["id", "name"], "limit": 1},
                )

                if not existing:
                    if verbosity >= 2:
                        self.stdout.write(
                            f"  NO PARTNER  {user.email} — not in Odoo yet, skipping."
                        )
                    skipped += 1
                    continue

                partner = existing[0]
                partner_id = partner["id"]
                current_name = (partner.get("name") or "").strip()

                if _is_placeholder(current_name, user):
                    # Build update payload
                    phone = ""
                    if hasattr(user, "phone") and user.phone:
                        phone = str(user.phone).strip()

                    write_vals = {"name": name}
                    if phone:
                        write_vals["phone"] = phone

                    sync._execute_rpc(
                        "res.partner",
                        "write",
                        [[partner_id], write_vals],
                    )

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  FIXED  {user.email}  "
                            f"'{current_name or '(blank)'}' → '{name}'"
                        )
                    )
                    fixed += 1

                    # Also update the name on any loan applications in Odoo
                    # that reference this applicant, so the list view refreshes
                    loan_ids = list(
                        user.loan_applications.exclude(
                            odoo_application_id__isnull=True
                        ).values_list("odoo_application_id", flat=True)
                    )
                    if loan_ids:
                        try:
                            sync._execute_rpc(
                                "berit.loan.application",
                                "write",
                                [loan_ids, {"applicant_id": partner_id}],
                            )
                            if verbosity >= 2:
                                self.stdout.write(
                                    f"         Re-linked {len(loan_ids)} loan(s) "
                                    f"to updated partner {partner_id}"
                                )
                        except Exception as link_err:
                            logger.warning(
                                "Could not re-link loans for %s: %s",
                                user.email,
                                link_err,
                            )

                else:
                    if verbosity >= 2:
                        self.stdout.write(
                            f"  OK     {user.email}  name='{current_name}' (no change needed)"
                        )
                    already_ok += 1

            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  ERROR  {user.email}: {exc}"))
                logger.exception("Error fixing partner for %s", user.email)
                errors += 1

        # ── Summary ──────────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(
            self.style.MIGRATE_HEADING("── Summary ──────────────────────────────")
        )
        self.stdout.write(f"  Users checked   : {total}")
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"  Would fix       : {fixed}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"  Fixed           : {fixed}"))
            self.stdout.write(f"  Already correct : {already_ok}")
        if skipped:
            self.stdout.write(self.style.WARNING(f"  Skipped         : {skipped}"))
        if errors:
            self.stdout.write(self.style.ERROR(f"  Errors          : {errors}"))
        self.stdout.write(f"\nRan at {timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')}")
