"""Send emails with the resume attached over SMTP (Gmail by default)."""

import mimetypes
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path


class MailError(Exception):
    pass


class Mailer:
    """Keeps one SMTP connection open for a batch of sends.

    with Mailer(user, app_password) as m:
        m.send(to, subject, body, resume_path)
    """

    def __init__(self, user: str, password: str, from_name: str = "", host: str = "smtp.gmail.com", port: int = 465):
        self.user = user.strip()
        self.password = password.replace(" ", "")  # Gmail shows app passwords in groups of 4
        self.from_name = from_name
        self.host = host
        self.port = int(port)
        self.server: smtplib.SMTP | None = None

    def __enter__(self):
        context = ssl.create_default_context()
        try:
            if self.port == 465:
                self.server = smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=30)
            else:
                self.server = smtplib.SMTP(self.host, self.port, timeout=30)
                self.server.starttls(context=context)
            self.server.login(self.user, self.password)
        except smtplib.SMTPAuthenticationError:
            raise MailError(
                "Login failed. For Gmail, use an App Password (not your normal password): "
                "Google Account → Security → 2-Step Verification → App passwords."
            )
        except (smtplib.SMTPException, OSError) as e:
            raise MailError(f"Couldn't connect to {self.host}:{self.port} - {e}")
        return self

    def __exit__(self, *exc):
        if self.server:
            try:
                self.server.quit()
            except smtplib.SMTPException:
                pass

    def send(self, to: str, subject: str, body: str, attachment: str | Path | None = None) -> None:
        msg = EmailMessage()
        msg["From"] = formataddr((self.from_name, self.user)) if self.from_name else self.user
        msg["To"] = to
        msg["Subject"] = subject
        msg["Reply-To"] = self.user
        msg["Message-ID"] = make_msgid(domain=self.user.split("@")[-1])
        msg.set_content(body)
        if attachment:
            path = Path(attachment)
            mime, _ = mimetypes.guess_type(path.name)
            maintype, subtype = (mime or "application/octet-stream").split("/", 1)
            msg.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)
        try:
            self.server.send_message(msg)
        except smtplib.SMTPRecipientsRefused:
            raise MailError(f"Recipient refused: {to}")
        except smtplib.SMTPException as e:
            raise MailError(str(e))
