"""Security logging helpers (US19)."""

import logging
import os

from flask import request

# US19: Security configuration and logging setup.
logging.basicConfig(level=logging.INFO)
security_logger = logging.getLogger("heatshield.security")
_security_handler = logging.FileHandler("security_events.log")
_security_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)
security_logger.addHandler(_security_handler)
security_logger.setLevel(logging.INFO)


def log_security_event(event_type, details="", ip_address=None):
    """Log a security-relevant event for audit purposes (US19 AC4).

    Writes to the file logger AND persists a row in SecurityAuditLog so that
    both mechanisms are available at rest.
    """
    from app.models.security_audit_log import SecurityAuditLog
    from app.database import db

    if ip_address is None:
        ip_address = request.remote_addr if request else "unknown"
    message = f"[{event_type}] IP={ip_address} {details}"
    security_logger.warning(message)

    # Persist to the database audit table so rows survive a log-rotation.
    try:
        row = SecurityAuditLog(
            event_type=event_type,
            ip_address=ip_address,
            details=details,
            timestamp=__import__("datetime", fromlist=["datetime", "timezone"]).datetime.now(
                __import__("datetime", fromlist=["datetime", "timezone"]).timezone.utc
            ),
        )
        db.session.add(row)
        db.session.commit()
    except Exception:
        # If the DB is unavailable fall back to file-only logging.
        db.session.rollback()


def sanitize_input(value):
    """Sanitise user input for XSS/injection prevention (US19 AC1).

    Returns a cleaned copy; does NOT HTML-escape — that happens at output time
    via contextual encoding in model ``to_dict()``, avoiding double-encoding.
    """
    if isinstance(value, str):
        return value.strip()
    return value


def encode_for_output(value):
    """Contextual HTML-encoding for safe display (US19 AC1).

    Applied at output time so the original data is preserved in storage and
    only encoded when rendered — prevents double-encoding and preserves
    legitimate characters such as parentheses, quotes, and angle brackets.
    """
    import html

    if isinstance(value, str):
        return html.escape(value)
    return value
