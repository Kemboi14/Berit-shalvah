# -*- coding: utf-8 -*-
"""
Management command: push_to_odoo
================================

Immediately pushes one or more Django loan applications to Odoo via the
PerfectOdooSync layer, **without** going through Celery.  Useful for:

* Re-syncing applications that were submitted before Celery was running
* Debugging sync failures interactively
* Initial bulk-load after a fresh Odoo installation

Usage examples
--------------
# Sync every application that has no Odoo ID yet:
    python manage.py push_to_odoo

# Sync every application regardless of sync status:
    python manage.py push_to_odoo --all

# Sync a specific application by its Django UUID:
    python manage.py push_to_odoo --id d5015ebe-72f6-4438-8d6f-f55a8915e533

# Sync all applications whose last SyncEvent failed:
    python manage.py push_to_odoo --failed

# Dry-run: show what would be synced without touching Odoo:
    python manage.py push_to_odoo --dry-run

# Increase verbosity to see full tracebacks:
    python manage.py push_to_odoo --verbosity 2
"""

import sys
import traceback
import uuid as _uuid_mod

from django.core.management.base import BaseCommand, CommandError
from django.db.models import OuterRef, Subquery
from django.utils import timezone


class Command(BaseCommand):
    help = (
        "Push loan application(s) from Django to Odoo immediately "
        "(bypasses Celery — runs synchronously in this process)."
    )

    # ------------------------------------------------------------------ #
    # Argument definitions                                                 #
    # ------------------------------------------------------------------ #

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--id",
            dest="application_id",
            metavar="UUID",
            help="Sync a single application by its Django UUID.",
        )
        group.add_argument(
            "--all",
            action="store_true",
            dest="sync_all",
            default=False,
            help="Sync ALL applications (including those already in Odoo).",
        )
        group.add_argument(
            "--failed",
            action="store_true",
            dest="sync_failed",
            default=False,
            help="Sync applications whose most-recent SyncEvent has status=failed.",
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            default=False,
            help="Print what would be synced without actually calling Odoo.",
        )
        parser.add_argument(
            "--status",
            dest="status_filter",
            metavar="STATUS",
            default=None,
            help=(
                "Only sync applications with this Django status "
                "(e.g. submitted, approved).  Can be combined with --all or --failed."
            ),
        )

    # ------------------------------------------------------------------ #
    # Entry point                                                          #
    # ------------------------------------------------------------------ #

    def handle(self, *args, **options):
        application_id = options["application_id"]
        sync_all = options["sync_all"]
        sync_failed = options["sync_failed"]
        dry_run = options["dry_run"]
        status_filter = options["status_filter"]
        verbosity = options["verbosity"]

        # Import here so manage.py --help doesn't require DB connection
        from apps.loans.models import LoanApplication
        from apps.loans.sync.webhook_models import SyncEvent

        # ── Resolve the queryset ────────────────────────────────────────
        if application_id:
            try:
                parsed_id = _uuid_mod.UUID(application_id)
            except ValueError:
                raise CommandError(f"'{application_id}' is not a valid UUID.")

            try:
                applications = LoanApplication.objects.filter(id=parsed_id)
                if not applications.exists():
                    raise CommandError(
                        f"No LoanApplication found with id={application_id}"
                    )
            except LoanApplication.DoesNotExist:
                raise CommandError(f"No LoanApplication found with id={application_id}")

        elif sync_all:
            applications = LoanApplication.objects.all()

        elif sync_failed:
            # Applications whose most-recent SyncEvent is in failed state
            latest_event_status = (
                SyncEvent.objects.filter(loan_application_id=OuterRef("id"))
                .order_by("-created_at")
                .values("status")[:1]
            )
            applications = LoanApplication.objects.annotate(
                last_sync_status=Subquery(latest_event_status)
            ).filter(last_sync_status="failed")

        else:
            # Default: applications not yet in Odoo (no odoo_application_id)
            applications = LoanApplication.objects.filter(
                odoo_application_id__isnull=True
            )

        # Optional status filter
        if status_filter:
            applications = applications.filter(status=status_filter)

        total = applications.count()

        if total == 0:
            self.stdout.write(self.style.WARNING("No matching applications found."))
            return

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"{'[DRY RUN] ' if dry_run else ''}"
                f"Syncing {total} application(s) to Odoo…"
            )
        )

        if dry_run:
            for app in applications.order_by("created_at"):
                self.stdout.write(
                    f"  Would sync: {app.reference_number} "
                    f"(id={app.id}, status={app.status}, "
                    f"odoo_id={app.odoo_application_id or 'none'})"
                )
            self.stdout.write(
                self.style.SUCCESS(f"Dry run complete — {total} item(s) listed.")
            )
            return

        # ── Connect to Odoo once for the whole batch ────────────────────
        try:
            from apps.loans.sync.perfect_sync import PerfectOdooSync

            sync = PerfectOdooSync()
        except Exception as conn_err:
            raise CommandError(
                f"Could not connect to Odoo: {conn_err}\n\n"
                "Check ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD in settings/.env"
            )

        # ── Iterate and sync ────────────────────────────────────────────
        success_count = 0
        failure_count = 0
        already_count = 0

        for app in applications.order_by("created_at"):
            label = f"{app.reference_number} (id={app.id})"

            try:
                result = sync.sync_loan_to_odoo(app)

                if result.get("locked"):
                    self.stdout.write(
                        self.style.WARNING(
                            f"  LOCKED  {label} — another sync in progress, skipped."
                        )
                    )
                    continue

                if result.get("success"):
                    odoo_id = result.get("odoo_id")
                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"  OK      {label} → Odoo id={odoo_id}")
                    )
                else:
                    failure_count += 1
                    error = result.get("error", "unknown error")
                    self.stdout.write(self.style.ERROR(f"  FAIL    {label}: {error}"))
                    if verbosity >= 2:
                        self.stderr.write(
                            f"          event_id={result.get('event_id')}"
                        )

            except Exception as exc:
                failure_count += 1
                self.stdout.write(self.style.ERROR(f"  ERROR   {label}: {exc}"))
                if verbosity >= 2:
                    self.stderr.write(traceback.format_exc())

        # ── Summary ─────────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(
            self.style.MIGRATE_HEADING("── Summary ──────────────────────────────")
        )
        self.stdout.write(f"  Total processed : {total}")
        self.stdout.write(self.style.SUCCESS(f"  Succeeded       : {success_count}"))
        if failure_count:
            self.stdout.write(self.style.ERROR(f"  Failed          : {failure_count}"))
        else:
            self.stdout.write(f"  Failed          : {failure_count}")

        self.stdout.write(f"\nRan at {timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if failure_count:
            # Exit with non-zero so CI/scripts can detect partial failures
            sys.exit(1)
