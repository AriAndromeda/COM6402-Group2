"""Support request model (US04c)."""

import html
from datetime import datetime, timezone

from app.database import db
from app.utils.encryption import decrypt_field


def encode_for_output(value):
    """Contextual HTML-encoding for safe display (US19 AC1)."""
    if isinstance(value, str):
        return html.escape(value)
    return value


class SupportRequest(db.Model):
    """A support request for the Heat Shield cooling-centres service.

    The ``area`` field is stored as provided (original casing preserved).
    Filter queries normalise area to lowercase so lookups are case-insensitive
    (e.g. ``?area=Bolton`` matches a record stored as "Bolton").
    """

    __tablename__ = "support_request"

    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    area = db.Column(db.String(80), nullable=False)
    priority = db.Column(db.String(20), nullable=False, default="medium")
    status = db.Column(db.String(20), nullable=False, default="new")
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        now = datetime.now(timezone.utc)
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now

    def to_dict(self):
        """Turn a database object into JSON-friendly data."""
        raw_description = decrypt_field(self.description)
        return {
            "id": self.id,
            "description": encode_for_output(raw_description),
            "category": self.category,
            "area": encode_for_output(self.area),
            "priority": self.priority,
            "status": self.status,
            "created_at": str(self.created_at),
            "updated_at": str(self.updated_at),
        }
