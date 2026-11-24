"""Clear seed data from the Heat Shield database.

Usage:
    python clear_seed_data.py              # remove all seeded records
    python clear_seed_data.py --keep-centres   # keep centres, remove requests & bookings

This script removes only the test data created by ``seed_data.py`` so you can
re-seed or insert your own records without touching production data.
"""

import argparse
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///heatshield.db"
db = SQLAlchemy(app)


class SupportRequest(db.Model):
    __tablename__ = "support_request"
    id = db.Column(db.Integer, primary_key=True)


class CoolingCentre(db.Model):
    __tablename__ = "cooling_centre"
    id = db.Column(db.Integer, primary_key=True)


class Booking(db.Model):
    __tablename__ = "booking"
    id = db.Column(db.Integer, primary_key=True)


def clear(keep_centres: bool = False):
    """Delete seeded records from the database."""
    with app.app_context():
        # Delete bookings first (foreign-key dependency).
        Booking.query.delete()
        print("  Removed all bookings.")

        # Delete support requests.
        SupportRequest.query.delete()
        print("  Removed all support requests.")

        if not keep_centres:
            CoolingCentre.query.delete()
            print("  Removed all cooling centres.")
        else:
            count = CoolingCentre.query.count()
            print(f"  Kept {count} cooling centre(s).")

        db.session.commit()
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
