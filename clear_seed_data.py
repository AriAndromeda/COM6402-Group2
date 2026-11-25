"""Clear seed data from the Heat Shield database.

Usage:
    python clear_seed_data.py              # remove all seeded records
    python clear_seed_data.py --keep-centres   # keep centres, remove requests & bookings

This script removes only the test data created by ``seed_data.py`` (records where
``seeded=True``) so you can re-seed or insert your own records without touching
genuine data.
"""

import argparse
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///heatshield.db"
db = SQLAlchemy(app)


# ── Schema migration helper ──────────────────────────────────────────
def _ensure_seeded_column(table_name: str):
    """Add the ``seeded`` column if it does not already exist.

    Safe to call multiple times — SQLite raises an error when the column
    is present, which we silently ignore.
    """
    with app.app_context():
        try:
            db.session.execute(
                db.text(f"ALTER TABLE {table_name} ADD COLUMN seeded BOOLEAN DEFAULT 0")
            )
            db.session.commit()
        except Exception:
            # Column already exists — nothing to do.
            pass


def ensure_seeded_columns():
    """Ensure all relevant tables have the ``seeded`` column."""
    _ensure_seeded_column("cooling_centre")
    _ensure_seeded_column("support_request")
    _ensure_seeded_column("booking")



class SupportRequest(db.Model):
    __tablename__ = "support_request"
    id = db.Column(db.Integer, primary_key=True)
    seeded = db.Column(db.Boolean, default=False)


class CoolingCentre(db.Model):
    __tablename__ = "cooling_centre"
    id = db.Column(db.Integer, primary_key=True)
    seeded = db.Column(db.Boolean, default=False)


class Booking(db.Model):
    __tablename__ = "booking"
    id = db.Column(db.Integer, primary_key=True)
    seeded = db.Column(db.Boolean, default=False)


def clear(keep_centres: bool = False):
    """Delete only seeded records from the database."""
    with app.app_context():
        # Ensure schema is compatible (adds ``seeded`` column if missing).
        ensure_seeded_columns()

        # Delete bookings first (foreign-key dependency).
        deleted_bookings = Booking.query.filter_by(seeded=True).delete()
        db.session.commit()
        print(f"  Removed {deleted_bookings} seeded booking(s).")

        # Delete support requests.
        deleted_requests = SupportRequest.query.filter_by(seeded=True).delete()
        db.session.commit()
        print(f"  Removed {deleted_requests} seeded request(s).")

        if not keep_centres:
            deleted_centres = CoolingCentre.query.filter_by(seeded=True).delete()
            db.session.commit()
            print(f"  Removed {deleted_centres} seeded centre(s).")
        else:
            count = CoolingCentre.query.filter_by(seeded=False).count()
            print(f"  Kept {count} non-seeded cooling centre(s).")

        print("\nDone! Seed data cleared.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clear seed data from the Heat Shield database.")
    parser.add_argument(
        "--keep-centres",
        action="store_true",
        help="Keep cooling centres; only remove requests and bookings.",
    )
    args = parser.parse_args()
    clear(keep_centres=args.keep_centres)
