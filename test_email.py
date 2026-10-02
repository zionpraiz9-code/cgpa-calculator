import argparse
import os
import re
import smtplib
import socket
import ssl
import sys
from email.message import EmailMessage
from email.utils import formataddr
from html import escape
from pathlib import Path

import requests
from dotenv import load_dotenv


ENV_FILE = Path(__file__).resolve().with_name(".env")
load_dotenv(ENV_FILE)


def env_value(name, default=""):
    return os.environ.get(name, default).strip().strip('"').strip("'").strip()


def html_email(body):
    escaped_body = escape(body)
    linked_body = re.sub(
        r"(https?://[^\s<]+)",
        r'<a href="\1" style="color:#2563eb;word-break:break-word">\1</a>',
        escaped_body,
    )
    return (
        '<div style="font-family:Arial,sans-serif;font-size:15px;line-height:1.6;'
        'color:#1f2937">' + linked_body.replace("\n", "<br>\n") + "</div>"
    )


def print_config():
    settings = {
        "MAIL_PROVIDER": (env_value("MAIL_PROVIDER", "smtp").lower(), False),
        "MAIL_SERVER": (env_value("MAIL_SERVER", "smtp.gmail.com"), False),
        "MAIL_PORT": (env_value("MAIL_PORT", "587"), False),
        "MAIL_USE_TLS": (env_value("MAIL_USE_TLS", "true"), False),
        "MAIL_SENDER_NAME": (env_value("MAIL_SENDER_NAME", "Z GRADE CALC"), False),
        "BREVO_API_KEY": (env_value("BREVO_API_KEY"), True),
        "MAIL_DEFAULT_SENDER": (env_value("MAIL_DEFAULT_SENDER"), True),
        "MAIL_USERNAME": (env_value("MAIL_USERNAME"), True),
        "MAIL_PASSWORD": (env_value("MAIL_PASSWORD"), True),
        "DEV_MODE": (env_value("DEV_MODE", "false"), False),
        "SECRET_KEY": (env_value("SECRET_KEY"), True),
    }
    for name, (value, secret) in settings.items():
        if secret:
            print(f"{name}: {'set' if value else 'MISSING'}")
        else:
            print(f"{name}: {value or 'MISSING'}")


def diagnoses(provider, error_text, exception, password):
    text = f"{error_text} {exception or ''}".lower()
    found = []

    def add_if(condition, message):
        if condition and message not in found:
            found.append(message)

    add_if(
        provider == "brevo_api" and ("401" in text or "invalid api key" in text or "unauthorized" in text),
        "The Brevo API key may be wrong, inactive, or copied with extra characters.",
    )
    add_if(
        "unrecognised ip" in text or "unrecognized ip" in text,
        "Brevo is blocking this server IP. Authorize the IP or disable IP blocking in Brevo Security settings.",
    )
    add_if(
        "sender" in text and any(term in text for term in ("verify", "verified", "validate", "not valid", "not allowed", "authenticate")),
        "Verify the sender email address in Brevo and use that exact address as MAIL_DEFAULT_SENDER.",
    )
    add_if(
        any(term in text for term in ("daily limit", "quota", "rate limit", "too many", "limit reached"))
        or (provider == "brevo_api" and "429" in text),
        "The provider's sending limit may have been reached; wait for the limit to reset or review the account quota.",
    )
    add_if(
        isinstance(exception, requests.exceptions.ProxyError) if exception else False,
        "A proxy configuration is preventing the HTTPS request. Check HTTPS_PROXY/HTTP_PROXY and network policy.",
    )
    add_if(
        isinstance(exception, (requests.exceptions.Timeout, socket.timeout, TimeoutError)) if exception else False,
        "The connection timed out. Check connectivity, firewall/proxy settings, and the provider endpoint.",
    )
    add_if(
        isinstance(exception, requests.exceptions.ConnectionError) if exception else False,
        "The HTTPS connection failed. Check proxy settings, DNS, outbound access, and the provider endpoint.",
    )
    add_if(
        isinstance(exception, smtplib.SMTPAuthenticationError) if exception else False,
        "SMTP authentication failed. Recheck the username and password; for Gmail use an App Password with 2-Step Verification.",
    )
    add_if(
        provider == "smtp" and (
            isinstance(exception, (smtplib.SMTPConnectError, ConnectionRefusedError))
            or any(term in text for term in ("connection refused", "cannot connect", "network is unreachable", "timed out"))
        ),
        "The SMTP port may be blocked by the host or network. Try the provider API or a permitted SMTP port.",
    )
    add_if(
        (
            isinstance(exception, (ssl.SSLError, smtplib.SMTPNotSupportedError))
            or any(term in text for term in ("wrong version number", "unknown protocol", "tls handshake", "ssl handshake"))
            or (provider == "smtp" and env_value("MAIL_PORT", "587") == "465" and env_value("MAIL_USE_TLS", "true").lower() in ("1", "true", "yes"))
        ) if exception else False,
        "The SMTP TLS/SSL mode may not match the port. Use STARTTLS on 587 or implicit SSL on 465, not both together.",
    )
    add_if(
        provider == "smtp" and bool(password) and any(char.isspace() for char in password),
        "The SMTP app password contains spaces. Copy it without grouping spaces before putting it in .env.",
    )
    return found


def send_test_email(recipient):
    provider = env_value("MAIL_PROVIDER", "smtp").lower()
    sender = env_value("MAIL_DEFAULT_SENDER", env_value("MAIL_USERNAME"))
    sender_name = env_value("MAIL_SENDER_NAME", "Z GRADE CALC")
    subject = "Z GRADE CALC email configuration test"
    body = "This is a test email from Z GRADE CALC.\n\nEmail delivery is configured."
    password = env_value("MAIL_PASSWORD")

    try:
        if provider == "brevo_api":
            api_key = env_value("BREVO_API_KEY")
            if not api_key:
                raise RuntimeError("BREVO_API_KEY is missing.")
            if not sender:
                raise RuntimeError("MAIL_DEFAULT_SENDER is missing.")
            response = requests.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={
                    "api-key": api_key,
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                json={
                    "sender": {"name": sender_name, "email": sender},
                    "to": [{"email": recipient}],
                    "subject": subject,
                    "textContent": body,
                    "htmlContent": html_email(body),
                },
                timeout=15,
            )
            if response.status_code not in (200, 201):
                raise RuntimeError(
                    f"Brevo API returned status {response.status_code}: {response.text[:300]}"
                )
        elif provider == "smtp":
            server = env_value("MAIL_SERVER", "smtp.gmail.com")
            port = int(env_value("MAIL_PORT", "587"))
            username = env_value("MAIL_USERNAME")
            if not username or not password:
                raise RuntimeError("SMTP credentials are missing.")
            if not sender:
                raise RuntimeError("MAIL_DEFAULT_SENDER is missing.")

            message = EmailMessage()
            message["Subject"] = subject
            message["From"] = formataddr((sender_name, sender))
            message["To"] = recipient
            message.set_content(body)
            message.add_alternative(html_email(body), subtype="html")

            with smtplib.SMTP(server, port, timeout=15) as smtp:
                smtp.ehlo()
                if env_value("MAIL_USE_TLS", "true").lower() in ("1", "true", "yes"):
                    smtp.starttls()
                    smtp.ehlo()
                smtp.login(username, password)
                smtp.send_message(message)
        else:
            raise RuntimeError("MAIL_PROVIDER must be 'brevo_api' or 'smtp'.")

        print(f"Test email sent successfully to {recipient} via {provider}.")
        return 0
    except Exception as exc:
        print(f"Email test failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        for diagnosis in diagnoses(provider, str(exc), exc, password):
            print(f"Diagnosis: {diagnosis}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description="Check or test Z GRADE CALC email settings.")
    parser.add_argument("recipient", nargs="?", help="Address to receive a real test email")
    parser.add_argument("--check-config", action="store_true", help="Show configuration status without sending")
    args = parser.parse_args()

    if args.check_config:
        print_config()
        return 0
    if not args.recipient:
        parser.error("recipient is required unless --check-config is used")
    return send_test_email(args.recipient)


if __name__ == "__main__":
    raise SystemExit(main())
