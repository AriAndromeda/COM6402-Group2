"""Seed script: populate the Heat Shield database with test data for dashboard testing.

Usage:
    python seed_data.py

Creates realistic support requests, cooling centres and bookings across
multiple areas so you can verify filters, counts and charts on the dashboard.

Running this script multiple times is safe — it skips records that already
exist (matched by name for centres and description for requests) and only
inserts new ones. Bookings reference actual database IDs rather than fixed
values, so they always point to valid records.
"""

from datetime import datetime, timezone

from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///heatshield.db"
db = SQLAlchemy(app)


# ── Schema migration helper ──────────────────────────────────────────

def _ensure_column(table_name: str, column_def: str):
    """Add a column if it does not already exist.

    ``column_def`` is the full ``ALTER TABLE … ADD COLUMN …`` fragment.
    Safe to call multiple times — SQLite raises an error when the column
    is present, which we silently ignore.
    """
    with app.app_context():
        try:
            db.session.execute(db.text(f"ALTER TABLE {table_name} {column_def}"))
            db.session.commit()
        except Exception:
            pass


def ensure_seeded_columns():
    """Ensure all relevant tables have the ``seeded`` column and timestamps."""
    _ensure_column("cooling_centre", "ADD COLUMN seeded BOOLEAN DEFAULT 0")
    _ensure_column("support_request", "ADD COLUMN seeded BOOLEAN DEFAULT 0")
    _ensure_column("booking", "ADD COLUMN seeded BOOLEAN DEFAULT 0")
    # Timestamps are needed by the INSERT statements below.
    _ensure_column(
        "support_request", "ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
    )
    _ensure_column(
        "support_request", "ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"
    )

# ── Full model definitions (for db.create_all table creation) ────────


class SupportRequest(db.Model):
    __tablename__ = "support_request"
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    area = db.Column(db.String(80), nullable=False)
    priority = db.Column(db.String(20), nullable=False, default="medium")
    status = db.Column(db.String(20), nullable=False, default="new")
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False)


class CoolingCentre(db.Model):
    __tablename__ = "cooling_centre"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    area = db.Column(db.String(80), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    spaces_available = db.Column(db.Integer, nullable=False)
    opening_hours = db.Column(db.String(80), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="open")


class Booking(db.Model):
    __tablename__ = "booking"
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
    # request_id and centre_id are resolved dynamically at runtime.
    {"request_desc": "Elderly resident needs help finding a cool place to stay during heatwave.", "centre_name": "Town Hall Community Centre",  "booking_date": "2025-07-15", "booking_time": "18:00", "spaces_required": 2},
    {"request_desc": "Family with young children seeking overnight cooling shelter.",            "centre_name": "St Mary's Church Hall",       "booking_date": "2025-07-16", "booking_time": "20:00", "spaces_required": 4},
    {"request_desc": "Need help accessing a public cooling space for mobility-impaired person.", "centre_name": "Oldham Community Hub",        "booking_date": "2025-07-14", "booking_time": "14:00", "spaces_required": 1},
]


# ── Main seeding logic ───────────────────────────────────────────────

def seed():
    """Create tables and insert test data."""
    with app.app_context():
        db.create_all()

        # Ensure schema is compatible (adds ``seeded`` column if missing).
        ensure_seeded_columns()

        now = datetime.now(timezone.utc)

        # Insert centres (skip duplicates matched by name, using raw SQL).
        created_centres = 0
        centre_id_map = {}  # name -> id for booking references.
        for c in CENTRES:
            row = db.session.execute(
                db.text("SELECT id FROM cooling_centre WHERE name = :name LIMIT 1"),
                {"name": c["name"]},
            ).first()
            if row is not None:
                centre_id_map[c["name"]] = row.id
                continue

            db.session.execute(
                db.text("""INSERT INTO cooling_centre
                           (name, area, capacity, spaces_available, opening_hours, status, seeded)
                           VALUES (:name, :area, :capacity, :spaces_available, :opening_hours, :status, 1)"""),
                {**c, "seeded": True},
            )
            created_centres += 1
        db.session.commit()

        for name, id_val in centre_id_map.items():
            print(f"  Centre (existing): {name} (id={id_val})")
        print(f"  Created {created_centres} new cooling centres.")

        # Insert support requests (skip duplicates matched by description).
        created_requests = 0
        request_id_map = {}  # description -> id for booking references.
        for r in REQUESTS:
            row = db.session.execute(
                db.text("SELECT id FROM support_request WHERE description = :desc LIMIT 1"),
                {"desc": r["description"]},
            ).first()
            if row is not None:
                request_id_map[r["description"]] = row.id
                continue

            db.session.execute(
                db.text("""INSERT INTO support_request
                           (description, category, area, priority, status, seeded, created_at, updated_at)
                           VALUES (:description, :category, :area, :priority, :status, 1, :now, :now)"""),
                {**r, "seeded": True, "now": now},
            )
            created_requests += 1
        db.session.commit()

        for desc, id_val in request_id_map.items():
            print(f"  Request (existing): {desc[:40]}... (id={id_val})")
        print(f"  Created {created_requests} new support requests.")

        # Insert bookings using dynamic ID lookups.
        created_bookings = 0
        for b in BOOKINGS:
            req_row = db.session.execute(
                db.text("SELECT id FROM support_request WHERE description = :desc LIMIT 1"),
                {"desc": b["request_desc"]},
            ).first()
            centre_row = db.session.execute(
                db.text("SELECT id FROM cooling_centre WHERE name = :name LIMIT 1"),
                {"name": b["centre_name"]},
            ).first()

            if req_row is None or centre_row is None:
                print(f"  Skipping booking — request or centre not found.")
                continue

            # Check for duplicate booking.
            dup = db.session.execute(
                db.text("""SELECT id FROM booking
                           WHERE request_id = :request_id AND centre_id = :centre_id
                           AND booking_date = :booking_date AND booking_time = :booking_time LIMIT 1"""),
                {"request_id": req_row.id, "centre_id": centre_row.id, **b},
            ).first()
            if dup is not None:
                continue

            db.session.execute(
                db.text("""INSERT INTO booking
                           (request_id, centre_id, booking_date, booking_time, spaces_required, status, seeded)
                           VALUES (:request_id, :centre_id, :booking_date, :booking_time, :spaces_required, 'confirmed', 1)"""),
                {"request_id": req_row.id, "centre_id": centre_row.id, **b},
            )
            created_bookings += 1
        db.session.commit()

        print(f"  Created {created_bookings} new bookings.")
        print("\nDone! Database seeded with test data.")


if __name__ == "__main__":
    seed()
