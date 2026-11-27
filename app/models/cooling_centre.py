"""Cooling centre model."""

import html

from app.database import db


def encode_for_output(value):
    """Contextual HTML-encoding for safe display (US19 AC1)."""
    if isinstance(value, str):
        return html.escape(value)
    return value


class CoolingCentre(db.Model):
    __tablename__ = "cooling_centre"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    area = db.Column(db.String(80), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    spaces_available = db.Column(db.Integer, nullable=False)
    opening_hours = db.Column(db.String(80), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="open")

    def to_dict(self):
        return {
            "id": self.id,
            "name": encode_for_output(self.name),
            "area": encode_for_output(self.area),
            "capacity": self.capacity,
            "spaces_available": self.spaces_available,
            "opening_hours": self.opening_hours,
            "status": self.status,
        }
