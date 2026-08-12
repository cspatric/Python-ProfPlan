"""Outbound email: one port, two adapters.

Sending is deliberately dumb here. Everything about *what* to send lives in the
module that owns the message (see ``auth/domain/emails.py``); this file only
knows how to hand bytes to an SMTP server, or to the log when no server is
configured.

The console adapter is not a test double. It is what runs in development and in
CI, where a mail server would be a dependency with no payoff: the link a
developer needs is right there in the log line.
"""

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MIMEMessage
from email.utils import formataddr

from app.core.config import get_settings

logger = logging.getLogger("app.email")


@dataclass(frozen=True, slots=True)
class EmailMessage:
    """A message ready to send. Plain text is mandatory, HTML is optional."""

    to: str
    subject: str
    text: str
    html: str | None = None


class EmailSender:
    """Port. Implementations must not raise for a merely undeliverable address."""

    def send(self, message: EmailMessage) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class ConsoleEmailSender(EmailSender):
    """Writes the message to the log instead of sending it.

    Used when EMAIL_ENABLED is false. The whole body is logged on purpose: in
    development the point of the email is the link inside it.
    """

    def send(self, message: EmailMessage) -> None:
        logger.info(
            "email not sent (EMAIL_ENABLED=false), body follows",
            extra={
                "email_to": message.to,
                "email_subject": message.subject,
                "email_body": message.text,
            },
        )


class SMTPEmailSender(EmailSender):
    """Sends through an SMTP server.

    Synchronous by design: this runs inside a Celery task, never inside a
    request, so blocking on the network is exactly what we want it to do.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        use_tls: bool,
        from_address: str,
        from_name: str,
        timeout: float,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._from_address = from_address
        self._from_name = from_name
        self._timeout = timeout

    def send(self, message: EmailMessage) -> None:
        mime = MIMEMessage()
        mime["Subject"] = message.subject
        mime["From"] = formataddr((self._from_name, self._from_address))
        mime["To"] = message.to
        mime.set_content(message.text)
        if message.html:
            mime.add_alternative(message.html, subtype="html")

        with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
            if self._use_tls:
                smtp.starttls()
            if self._username:
                smtp.login(self._username, self._password)
            smtp.send_message(mime)

        logger.info(
            "email sent",
            extra={"email_to": message.to, "email_subject": message.subject},
        )


def get_email_sender() -> EmailSender:
    """The adapter for the current configuration."""
    settings = get_settings()
    if not settings.email_enabled:
        return ConsoleEmailSender()
    return SMTPEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        use_tls=settings.smtp_use_tls,
        from_address=settings.email_from_address,
        from_name=settings.email_from_name,
        timeout=settings.smtp_timeout_seconds,
    )
