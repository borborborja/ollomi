"""Outbound mail for password recovery in the Ollomi selfhost fork.

The fork delivers mail exclusively through the operator-supplied SMTP settings
(`OLLOMI_SMTP_*` env-only, see `selfhost.config`); there are no third-party
mail providers and no per-tenant overrides from the database. Everything is
constructed inside the functions: importing this module performs no network
IO and requires no configuration.

Never log the reset token, the full reset link, or the recipient address.
"""

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from .config import settings

logger = logging.getLogger(__name__)

_TEMPLATES = {
    "reset": {
        "ca": {
            "subject": "Restableix la teva contrasenya d'Ollomi",
            "body": (
                "Has demanat restablir la contrasenya del teu compte d'Ollomi.\n"
                "Obre aquest enllaç per definir-ne una de nova (és d'un sol ús i caduca aviat):\n\n"
                "{link}\n\n"
                "Si no has estat tu, ignora aquest correu."
            ),
        },
        "es": {
            "subject": "Restablece tu contraseña de Ollomi",
            "body": (
                "Has solicitado restablecer la contraseña de tu cuenta de Ollomi.\n"
                "Abre este enlace para definir una nueva (es de un solo uso y caduca pronto):\n\n"
                "{link}\n\n"
                "Si no has sido tú, ignora este correo."
            ),
        },
        "en": {
            "subject": "Reset your Ollomi password",
            "body": (
                "You requested a password reset for your Ollomi account.\n"
                "Open this link to choose a new password (single use, expires soon):\n\n"
                "{link}\n\n"
                "If this was not you, ignore this email."
            ),
        },
    },
    "changed": {
        "ca": {
            "subject": "La teva contrasenya d'Ollomi ha canviat",
            "body": (
                "La contrasenya del teu compte d'Ollomi s'ha canviat correctament.\n"
                "S'han tancat totes les altres sessions.\n\n"
                "Si no has estat tu, contacta immediatament amb l'administrador del servidor."
            ),
        },
        "es": {
            "subject": "Tu contraseña de Ollomi ha cambiado",
            "body": (
                "La contraseña de tu cuenta de Ollomi se ha cambiado correctamente.\n"
                "Se han cerrado el resto de sesiones.\n\n"
                "Si no has sido tú, contacta inmediatamente con el administrador del servidor."
            ),
        },
        "en": {
            "subject": "Your Ollomi password has changed",
            "body": (
                "The password for your Ollomi account was changed successfully.\n"
                "All other sessions were signed out.\n\n"
                "If this was not you, contact the server administrator immediately."
            ),
        },
    },
}

_DEFAULT_LANGUAGE = "en"


def _template(kind: str, language: str) -> dict:
    templates = _TEMPLATES[kind]
    return templates.get(language) or templates[_DEFAULT_LANGUAGE]


def _safe_header(value: str) -> bool:
    return "\r" not in value and "\n" not in value


def configured() -> bool:
    return bool(settings().smtp_host)


def send(message: EmailMessage) -> bool:
    config = settings()
    if not config.smtp_host:
        logger.warning("mail: delivery requested but SMTP is not configured")
        return False
    try:
        if config.smtp_security == "ssl":
            server = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=config.smtp_timeout)
        else:
            server = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=config.smtp_timeout)
        with server:
            if config.smtp_security == "starttls":
                server.starttls()
            if config.smtp_username:
                server.login(config.smtp_username, config.smtp_password.get_secret_value())
            server.send_message(message)
        logger.info("mail: message delivered (%s)", config.smtp_security)
        return True
    except (smtplib.SMTPException, OSError) as error:
        logger.warning("mail: delivery failed (%s: %s)", type(error).__name__, error.__class__.__name__)
        return False


def _build(kind: str, to: str, language: str, **fields: str) -> EmailMessage | None:
    config = settings()
    if not _safe_header(to):
        logger.warning("mail: refused to send, unsafe recipient header")
        return None
    template = _template(kind, language)
    message = EmailMessage()
    for header, value in (("To", to), ("Subject", template["subject"])):
        if not _safe_header(value):
            logger.warning("mail: refused to send, unsafe %s header", header)
            return None
        message[header] = value
    _, from_address = parseaddr(config.smtp_from)
    if not from_address or not _safe_header(config.smtp_from):
        logger.warning("mail: refused to send, unsafe From header")
        return None
    message["From"] = config.smtp_from
    if config.smtp_reply_to:
        if not _safe_header(config.smtp_reply_to):
            logger.warning("mail: refused to send, unsafe Reply-To header")
            return None
        message["Reply-To"] = config.smtp_reply_to
    body = template["body"].format(**fields)
    message.set_content(body)
    return message


def send_password_reset_email(to: str, link: str, language: str) -> bool:
    message = _build("reset", to, language, link=link)
    if message is None:
        return False
    return send(message)


def send_password_changed_email(to: str, language: str) -> bool:
    message = _build("changed", to, language)
    if message is None:
        return False
    return send(message)
