# -*- coding: utf-8 -*-
"""
Webhook models for real-time Odoo-Django synchronization
"""

import hashlib
import json
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class SyncEvent(models.Model):
    """
    Tracks all synchronization events between Django and Odoo
    """

    class EventType(models.TextChoices):
        # Django -> Odoo
        LOAN_CREATED = "loan_created", _("Loan Created")
        LOAN_UPDATED = "loan_updated", _("Loan Updated")
        LOAN_STATUS_CHANGED = "loan_status_changed", _("Loan Status Changed")
        DOCUMENT_CREATED = "document_created", _("Document Created")
        COLLATERAL_CREATED = "collateral_created", _("Collateral Created")
        GUARANTOR_CREATED = "guarantor_created", _("Guarantor Created")
        USER_CREATED = "user_created", _("User Created")

        # Odoo -> Django
        ODOO_LOAN_UPDATED = "odoo_loan_updated", _("Odoo Loan Updated")
        ODOO_STATUS_CHANGED = "odoo_status_changed", _("Odoo Status Changed")
        ODOO_DISBURSED = "odoo_disbursed", _("Odoo Disbursed")
        ODOO_REPAYMENT_RECORDED = (
            "odoo_repayment_recorded",
            _("Odoo Repayment Recorded"),
        )

    class Direction(models.TextChoices):
        DJANGO_TO_ODOO = "django_to_odoo", _("Django to Odoo")
        ODOO_TO_DJANGO = "odoo_to_django", _("Odoo to Django")

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PROCESSING = "processing", _("Processing")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed")
        RETRY = "retry", _("Retry")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(
        _("Event Type"), max_length=50, choices=EventType.choices
    )
    direction = models.CharField(
        _("Direction"), max_length=20, choices=Direction.choices
    )
    status = models.CharField(
        _("Status"), max_length=20, choices=Status.choices, default=Status.PENDING
    )

    # Data payload
    payload = models.JSONField(_("Payload"), default=dict)
    response_data = models.JSONField(_("Response Data"), default=dict, blank=True)

    # References
    loan_application_id = models.UUIDField(
        _("Loan Application ID"), null=True, blank=True
    )
    odoo_record_id = models.IntegerField(_("Odoo Record ID"), null=True, blank=True)

    # Timing
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    started_at = models.DateTimeField(_("Started At"), null=True, blank=True)
    completed_at = models.DateTimeField(_("Completed At"), null=True, blank=True)

    # Retry tracking
    retry_count = models.IntegerField(_("Retry Count"), default=0)
    max_retries = models.IntegerField(_("Max Retries"), default=3)
    next_retry_at = models.DateTimeField(_("Next Retry At"), null=True, blank=True)

    # Error tracking
    error_message = models.TextField(_("Error Message"), blank=True)
    error_traceback = models.TextField(_("Error Traceback"), blank=True)

    # Conflict resolution
    source_timestamp = models.DateTimeField(
        _("Source Timestamp"),
        null=True,
        blank=True,
        help_text=_("When the change was made in the source system"),
    )
    target_timestamp = models.DateTimeField(
        _("Target Timestamp"),
        null=True,
        blank=True,
        help_text=_("When the change was applied in the target system"),
    )

    # Webhook verification
    webhook_signature = models.CharField(
        _("Webhook Signature"), max_length=64, blank=True
    )
    signature_verified = models.BooleanField(_("Signature Verified"), default=False)

    class Meta:
        verbose_name = _("Sync Event")
        verbose_name_plural = _("Sync Events")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["event_type", "direction"]),
            models.Index(fields=["loan_application_id"]),
        ]

    def __str__(self):
        return f"{self.event_type} - {self.direction} - {self.status}"

    def mark_started(self):
        """Mark event as started processing"""
        self.status = self.Status.PROCESSING
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at"])

    def mark_completed(self, response_data=None):
        """Mark event as completed"""
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.target_timestamp = timezone.now()
        if response_data:
            self.response_data = response_data
        self.save(
            update_fields=[
                "status",
                "completed_at",
                "target_timestamp",
                "response_data",
            ]
        )

    def mark_failed(self, error_message, traceback=""):
        """Mark event as failed"""
        self.status = self.Status.FAILED
        self.completed_at = timezone.now()
        self.error_message = error_message
        self.error_traceback = traceback
        self.save(
            update_fields=["status", "completed_at", "error_message", "error_traceback"]
        )

    def should_retry(self):
        """Check if event should be retried"""
        return self.retry_count < self.max_retries and self.status in [
            self.Status.FAILED,
            self.Status.RETRY,
        ]

    def schedule_retry(self, delay_seconds=60):
        """Schedule a retry attempt"""
        self.retry_count += 1
        self.status = self.Status.RETRY
        self.next_retry_at = timezone.now() + timezone.timedelta(seconds=delay_seconds)
        self.save(update_fields=["retry_count", "status", "next_retry_at"])

    @property
    def duration(self):
        """Get processing duration in seconds"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def is_stale(self):
        """Check if event is stale (pending for too long)"""
        if self.status == self.Status.PENDING:
            age = timezone.now() - self.created_at
            return age.total_seconds() > 300  # 5 minutes
        return False


class WebhookSubscription(models.Model):
    """
    Stores webhook subscriptions for real-time notifications
    """

    class Event(models.TextChoices):
        LOAN_CREATED = "loan.created", _("Loan Created")
        LOAN_UPDATED = "loan.updated", _("Loan Updated")
        LOAN_STATUS_CHANGED = "loan.status.changed", _("Loan Status Changed")
        LOAN_APPROVED = "loan.approved", _("Loan Approved")
        LOAN_REJECTED = "loan.rejected", _("Loan Rejected")
        LOAN_DISBURSED = "loan.disbursed", _("Loan Disbursed")
        REPAYMENT_RECORDED = "repayment.recorded", _("Repayment Recorded")
        USER_CREATED = "user.created", _("User Created")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.CharField(_("Event"), max_length=50, choices=Event.choices)
    webhook_url = models.URLField(_("Webhook URL"), max_length=500)
    secret_key = models.CharField(
        _("Secret Key"),
        max_length=64,
        editable=False,
        help_text=_("Key used to sign webhook payloads"),
    )
    is_active = models.BooleanField(_("Active"), default=True)

    # Tracking
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    last_triggered_at = models.DateTimeField(
        _("Last Triggered At"),
        blank=True,
        null=True,
    )
    total_triggers = models.IntegerField(_("Total Triggers"), default=0)
    successful_triggers = models.IntegerField(_("Successful Triggers"), default=0)
    failed_triggers = models.IntegerField(_("Failed Triggers"), default=0)

    # Headers to send with webhook
    custom_headers = models.JSONField(_("Custom Headers"), default=dict, blank=True)

    class Meta:
        verbose_name = _("Webhook Subscription")
        verbose_name_plural = _("Webhook Subscriptions")
        ordering = ["-created_at"]
        unique_together = ["event", "webhook_url"]

    def __str__(self):
        return f"{self.event} -> {self.webhook_url}"

    def save(self, *args, **kwargs):
        if not self.secret_key:
            self.secret_key = self._generate_secret_key()
        super().save(*args, **kwargs)

    def _generate_secret_key(self):
        """Generate a secure secret key"""
        return hashlib.sha256(
            f"{timezone.now().isoformat()}{settings.SECRET_KEY}".encode()
        ).hexdigest()[:64]

    def verify_signature(self, payload, signature):
        """Verify webhook payload signature"""
        expected = hashlib.sha256(f"{payload}{self.secret_key}".encode()).hexdigest()
        return signature == expected

    def record_trigger(self, success=True):
        """Record a webhook trigger"""
        self.last_triggered_at = timezone.now()
        self.total_triggers += 1
        if success:
            self.successful_triggers += 1
        else:
            self.failed_triggers += 1
        self.save(
            update_fields=[
                "last_triggered_at",
                "total_triggers",
                "successful_triggers",
                "failed_triggers",
            ]
        )

    @property
    def success_rate(self):
        """Calculate success rate percentage"""
        if self.total_triggers == 0:
            return 0
        return (self.successful_triggers / self.total_triggers) * 100

    @property
    def is_healthy(self):
        """Check if webhook is healthy (recently succeeding)"""
        if self.total_triggers == 0:
            return True
        return self.success_rate >= 80


class SyncLock(models.Model):
    """
    Prevents concurrent sync operations for the same resource
    """

    class LockType(models.TextChoices):
        LOAN_APPLICATION = "loan_application", _("Loan Application")
        DOCUMENT = "document", _("Document")
        COLLATERAL = "collateral", _("Collateral")
        GUARANTOR = "guarantor", _("Guarantor")
        USER = "user", _("User")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lock_type = models.CharField(
        _("Lock Type"), max_length=30, choices=LockType.choices
    )
    resource_id = models.CharField(_("Resource ID"), max_length=100)
    locked_by = models.CharField(
        _("Locked By"),
        max_length=100,
        help_text=_("Process or task that holds the lock"),
    )
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    expires_at = models.DateTimeField(_("Expires At"))
    is_released = models.BooleanField(_("Released"), default=False)

    class Meta:
        verbose_name = _("Sync Lock")
        verbose_name_plural = _("Sync Locks")
        unique_together = ["lock_type", "resource_id"]
        indexes = [
            models.Index(fields=["lock_type", "resource_id"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"{self.lock_type}:{self.resource_id} ({self.locked_by})"

    def is_expired(self):
        """Check if lock has expired"""
        return timezone.now() > self.expires_at

    def release(self):
        """Release the lock"""
        self.is_released = True
        self.save(update_fields=["is_released"])

    @classmethod
    def acquire(cls, lock_type, resource_id, locked_by, ttl_seconds=300):
        """Acquire a lock for a resource.

        Returns True if the lock was acquired, False if a valid (non-expired,
        non-released) lock already exists for this resource.

        Uses update_or_create so that stale/expired rows are overwritten in a
        single atomic statement, avoiding IntegrityError from the
        unique_together constraint on (lock_type, resource_id).
        """
        from django.db import IntegrityError

        resource_id_str = str(resource_id)
        now = timezone.now()

        # Check for an existing lock that is still valid
        existing = cls.objects.filter(
            lock_type=lock_type,
            resource_id=resource_id_str,
            is_released=False,
            expires_at__gt=now,
        ).first()

        if existing:
            return False

        # No valid lock exists — delete any stale rows for this resource
        # (expired or already released) before creating a fresh one.
        cls.objects.filter(
            lock_type=lock_type,
            resource_id=resource_id_str,
        ).delete()

        try:
            cls.objects.create(
                lock_type=lock_type,
                resource_id=resource_id_str,
                locked_by=locked_by,
                expires_at=now + timezone.timedelta(seconds=ttl_seconds),
            )
        except IntegrityError:
            # Another process created a lock between our delete and create
            # (genuine race condition) — treat as lock-not-acquired.
            return False

        return True

    @classmethod
    def release_all_expired(cls):
        """Release all expired locks"""
        expired = cls.objects.filter(is_released=False, expires_at__lt=timezone.now())
        count = expired.count()
        expired.update(is_released=True)
        return count


class SyncConflict(models.Model):
    """
    Tracks and resolves sync conflicts
    """

    class Resolution(models.TextChoices):
        PENDING = "pending", _("Pending Resolution")
        USE_DJANGO = "use_django", _("Use Django Version")
        USE_ODOO = "use_odoo", _("Use Odoo Version")
        MERGED = "merged", _("Manually Merged")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resource_type = models.CharField(_("Resource Type"), max_length=50)
    resource_id = models.CharField(_("Resource ID"), max_length=100)
    django_data = models.JSONField(_("Django Data"))
    odoo_data = models.JSONField(_("Odoo Data"))
    conflict_fields = models.JSONField(_("Conflicting Fields"), default=list)

    django_modified_at = models.DateTimeField(_("Django Modified At"))
    odoo_modified_at = models.DateTimeField(_("Odoo Modified At"))

    resolution = models.CharField(
        _("Resolution"),
        max_length=20,
        choices=Resolution.choices,
        default=Resolution.PENDING,
    )
    resolved_at = models.DateTimeField(_("Resolved At"), null=True, blank=True)
    resolved_by = models.CharField(_("Resolved By"), max_length=100, blank=True)
    resolution_notes = models.TextField(_("Resolution Notes"), blank=True)

    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    class Meta:
        verbose_name = _("Sync Conflict")
        verbose_name_plural = _("Sync Conflicts")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Conflict: {self.resource_type}:{self.resource_id}"

    def auto_resolve(self):
        """Auto-resolve based on timestamps (last-write-wins)"""
        if self.django_modified_at > self.odoo_modified_at:
            self.resolution = self.Resolution.USE_DJANGO
        else:
            self.resolution = self.Resolution.USE_ODOO
        self.resolved_at = timezone.now()
        self.resolution_notes = "Auto-resolved: using most recent version"
        self.save()
        return self.resolution
