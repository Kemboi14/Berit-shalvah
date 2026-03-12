# -*- coding: utf-8 -*-
"""
Celery tasks for accounts app
"""

import logging

from celery import shared_task
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def cleanup_expired_sessions():
    """
    Delete all expired sessions from the database.

    Django's session engine does not automatically purge expired rows —
    they accumulate until either this task or the management command
    `clearsessions` removes them.  Running this every 6 hours keeps the
    django_session table lean without hammering the DB.
    """
    try:
        # Use Django's built-in session store method which issues a single
        # DELETE WHERE expire_date < NOW() query — no Python-side iteration.
        SessionStore.clear_expired()
        logger.info("cleanup_expired_sessions: expired sessions cleared")
        return "Expired sessions cleared"
    except Exception as exc:
        logger.error(f"cleanup_expired_sessions failed: {exc}", exc_info=True)
        return f"Error clearing expired sessions: {exc}"


@shared_task
def send_welcome_email(user_id):
    """
    Send a welcome email to a newly registered user.

    Imported here so the accounts app owns its own notification tasks and
    does not depend on the loans app task module.
    """
    try:
        from django.conf import settings
        from django.contrib.auth import get_user_model
        from django.core.mail import send_mail
        from django.template.loader import render_to_string

        User = get_user_model()
        user = User.objects.get(pk=user_id)

        context = {
            "user": user,
            "portal_settings": getattr(settings, "PORTAL_SETTINGS", {}),
        }

        try:
            html_message = render_to_string("berit/emails/welcome.html", context)
        except Exception:
            html_message = None

        plain_message = (
            f"Dear {user.get_full_name() or user.email},\n\n"
            f"Welcome to Berit Shalvah Financial Services!\n\n"
            f"You can now log in and apply for a loan through our portal.\n\n"
            f"Regards,\nBerit Shalvah Financial Services"
        )

        send_mail(
            subject="Welcome to Berit Shalvah Financial Services",
            message=plain_message,
            from_email=getattr(
                settings, "DEFAULT_FROM_EMAIL", "noreply@beritshalvah.co.ke"
            ),
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=True,
        )

        logger.info(f"send_welcome_email: sent to {user.email}")
        return f"Welcome email sent to {user.email}"

    except Exception as exc:
        logger.error(
            f"send_welcome_email failed for user {user_id}: {exc}", exc_info=True
        )
        return f"Error sending welcome email: {exc}"


@shared_task
def deactivate_unverified_accounts(days=30):
    """
    Deactivate accounts that have remained unverified for more than
    `days` days.  Runs as a periodic housekeeping task.
    """
    try:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        cutoff = timezone.now() - timezone.timedelta(days=days)

        qs = User.objects.filter(
            is_verified=False,
            is_active=True,
            date_joined__lt=cutoff,
        )
        count = qs.count()
        qs.update(is_active=False)

        logger.info(
            f"deactivate_unverified_accounts: deactivated {count} accounts "
            f"unverified for >{days} days"
        )
        return f"Deactivated {count} unverified accounts"

    except Exception as exc:
        logger.error(f"deactivate_unverified_accounts failed: {exc}", exc_info=True)
        return f"Error deactivating unverified accounts: {exc}"
