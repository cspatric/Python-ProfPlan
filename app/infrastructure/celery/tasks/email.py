"""Celery task that delivers one email.

Sending happens here rather than in the request for the usual reason: an SMTP
server that is slow or down would otherwise become our latency and our error.
A password reset that is accepted and queued is honest, because the user is
told to check their inbox, not that the mail has arrived.

Retries are generous and slow. Mail servers fail transiently far more often
than permanently, and nobody is waiting on this in a request.
"""

import logging

from app.infrastructure.celery import dead_letter
from app.infrastructure.celery.worker import celery_app
from app.infrastructure.email.sender import EmailMessage, get_email_sender

logger = logging.getLogger("app.email")

_MAX_RETRIES = 5


@celery_app.task(bind=True, name="emails.send", max_retries=_MAX_RETRIES)
def send_email(self, to: str, subject: str, text: str, html: str | None = None) -> None:
    """Deliver one message, retrying transient SMTP failures."""
    try:
        get_email_sender().send(
            EmailMessage(to=to, subject=subject, text=text, html=html)
        )
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            # Give up loudly: the user was told to check their inbox and there
            # is nothing there. This is what the CeleryTaskFailures alert sees.
            logger.error("email delivery failed permanently: %s", exc)
            # The address is kept so a replay can reach the person who never
            # got their reset link; the body is not, because a dead letter
            # list is not a place to keep a password reset token.
            dead_letter.record(
                task=self.name,
                args=(to, subject),
                error=str(exc),
                retries=self.request.retries,
            )
            raise
        # 30s, 1m, 2m, 4m, 8m.
        raise self.retry(exc=exc, countdown=30 * 2**self.request.retries) from exc
