"""Email delivery for the gateway's alert emails. SMTP when configured; otherwise each email is recorded as `logged`
(visible in the System view) so the chain can be demonstrated without a mail account."""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage


class Mailer:
    def __init__(self, smtp):
        self.smtp = smtp

    @property
    def enabled(self) -> bool:
        return bool(self.smtp.host)

    def send(self, to: str, subject: str, body: str) -> tuple[str, str]:
        if not self.enabled:
            return "logged", ""
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.smtp.sender, to, subject
        msg.set_content(body)
        try:
            with smtplib.SMTP(self.smtp.host, self.smtp.port, timeout=10) as s:
                if self.smtp.starttls:
                    s.starttls(context=ssl.create_default_context())
                if self.smtp.user:
                    s.login(self.smtp.user, self.smtp.password)
                s.send_message(msg)
            return "sent", ""
        except Exception as e:          # delivery errors are shown, never raised into the ingest path
            return "failed", repr(e)[:300]
