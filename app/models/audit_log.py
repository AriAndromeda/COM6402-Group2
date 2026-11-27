"""Audit log model (US06)."""

from datetime import datetime, timezone

from app.database import db


class AuditLog(db.Model):
    """Record successful actions performed by staff."""

    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)
    staff_user_id = db.Column(
        db.Integer, db.ForeignKey("staff_user.id"), nullable=False
    )
    action = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(50), nullable=False)
    resource_id = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "staff_user_id": self.staff_user_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "timestamp": self.timestamp.isoformat(),
        }
