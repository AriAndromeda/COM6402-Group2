"""Security audit log model (US19)."""

from datetime import datetime, timezone

from app.database import db


class SecurityAuditLog(db.Model):
    """Record security-relevant events for audit purposes (US19 AC4)."""

    __tablename__ = "security_audit_log"

    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(50), nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False)
