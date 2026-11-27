"""Booking model (US04c)."""

from app.database import db


class Booking(db.Model):
    __tablename__ = "booking"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(
        db.Integer, db.ForeignKey("support_request.id"), nullable=False
    )
    centre_id = db.Column(
        db.Integer, db.ForeignKey("cooling_centre.id"), nullable=False
    )
    booking_date = db.Column(db.String(20), nullable=False)
    booking_time = db.Column(db.String(20), nullable=False)
    spaces_required = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="confirmed")

    def to_dict(self):
        return {
            "id": self.id,
            "request_id": self.request_id,
            "centre_id": self.centre_id,
            "booking_date": self.booking_date,
            "booking_time": self.booking_time,
            "spaces_required": self.spaces_required,
            "status": self.status,
        }
