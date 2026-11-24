"""Seed script: populate the Heat Shield database with test data for dashboard testing.

Usage:
    python seed_data.py

Creates realistic support requests, cooling centres and bookings across
multiple areas so you can verify filters, counts and charts on the dashboard.
"""

import os
from datetime import datetime, timezone

from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///heatshield.db"
db = SQLAlchemy(app)


# ── Reuse the same models from app.py ────────────────────────────────
class SupportRequest(db.Model):
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


class CoolingCentre(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    area = db.Column(db.String(80), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    spaces_available = db.Column(db.Integer, nullable=False)
    opening_hours = db.Column(db.String(80), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="open")


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("support_request.id"), nullable=False)
    centre_id = db.Column(db.Integer, db.ForeignKey("cooling_centre.id"), nullable=False)
    booking_date = db.Column(db.String(20), nullable=False)
    booking_time = db.Column(db.String(20), nullable=False)
    spaces_required = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="confirmed")


# ── Seed data definitions ────────────────────────────────────────────

CENTRES = [
    {"name": "Town Hall Community Centre",  "area": "Bolton",       "capacity": 50, "spaces_available": 50, "opening_hours": "Mon-Sun 8am-8pm", "status": "open"},
    {"name": "St Mary's Church Hall",       "area": "Bury",         "capacity": 30, "spaces_available": 30, "opening_hours": "Mon-Fri 9am-5pm",   "status": "open"},
    {"name": "Prestwich Leisure Centre",     "area": "Prestwich",    "capacity": 40, "spaces_available": 25, "opening_hours": "Daily 7am-10pm",      "status": "open"},
    {"name": "Rochdale Civic Hall",         "area": "Rochdale",     "capacity": 60, "spaces_available": 60, "opening_hours": "Mon-Sun 8am-9pm",     "status": "open"},
    {"name": "Oldham Community Hub",        "area": "Oldham",       "capacity": 35, "spaces_available": 10, "opening_hours": "Tue-Sat 10am-6pm",    "status": "open"},
    {"name": "Salford Sports Centre",       "area": "Salford",      "capacity": 45, "spaces_available": 45, "opening_hours": "Daily 6am-11pm",      "status": "open"},
    {"name": "Altrinchall Memorial Hall",   "area": "Altrincham",   "capacity": 20, "spaces_available": 20, "opening_hours": "Mon-Fri 9am-5pm",     "status": "closed"},
]

REQUESTS = [
    {"description": "Elderly resident needs help finding a cool place to stay during heatwave.", "category": "welfare",   "area": "Bolton",       "priority": "high",    "status": "new"},
    {"description": "Family with young children seeking overnight cooling shelter.",            "category": "cooling",   "area": "Bury",         "priority": "critical","status": "in progress"},
    {"description": "Request for assistance with installing temporary window blinds.",          "category": "practical-assistance", "area": "Prestwich",  "priority": "medium", "status": "new"},
    {"description": "Senior citizen reports feeling unwell due to high indoor temperatures.",   "category": "medical",   "area": "Rochdale",     "priority": "critical","status": "in progress"},
    {"description": "Need help accessing a public cooling space for mobility-impaired person.", "category": "welfare",   "area": "Oldham",       "priority": "high",    "status": "completed"},
    {"description": "Multiple neighbours reporting no fan or AC in block of flats.",           "category": "cooling",   "area": "Salford",      "priority": "medium",  "status": "new"},
    {"description": "Request for water delivery to isolated elderly person.",                   "category": "welfare",   "area": "Altrincham",   "priority": "high",    "status": "in progress"},
    {"description": "Community centre staff need guidance on heat safety protocols.",           "category": "practical-assistance", "area": "Bolton",  "priority": "low",     "status": "completed"},
    {"description": "Childcare facility requesting air-conditioning repair referral.",          "category": "practical-assistance", "area": "Bury",    "priority": "medium",  "status": "new"},
    {"description": "Homeless individual seeking emergency cooling accommodation.",             "category": "welfare",   "area": "Rochdale",     "priority": "critical","status": "new"},
]

BOOKINGS = [
    {"request_id": 1, "centre_id": 1, "booking_date": "2025-07-15", "booking_time": "18:00", "spaces_required": 2},
    {"request_id": 2, "centre_id": 2, "booking_date": "2025-07-16", "booking_time": "20:00", "spaces_required": 4},
    {"request_id": 5, "centre_id": 5, "booking_date": "2025-07-14", "booking_time": "14:00", "spaces_required": 1},
]


# ── Main seeding logic ───────────────────────────────────────────────

def seed():
    """Create tables and insert test data."""
    with app.app_context():
        db.create_all()

        # Insert centres
        for c in CENTRES:
            centre = CoolingCentre(**c)
            db.session.add(centre)
        db.session.commit()
        print(f"  Created {len(CENTRES)} cooling centres.")

        # Insert support requests
        for r in REQUESTS:
            req = SupportRequest(**r)
            db.session.add(req)
        db.session.commit()
        print(f"  Created {len(REQUESTS)} support requests.")

        # Insert bookings (referencing the above IDs)
        for b in BOOKINGS:
            booking = Booking(**b)
            db.session.add(booking)
        db.session.commit()
        print(f"  Created {len(BOOKINGS)} bookings.")

        print("\nDone! Database seeded with test data.")


if __name__ == "__main__":
    seed()
