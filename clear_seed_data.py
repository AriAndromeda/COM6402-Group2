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
    # Timestamps are needed by the DELETE statements (they reference seeded).
    _ensure_column(
        "support_request", "ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
    )
    _ensure_column(
        "support_request", "ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"
    )

# ── Minimal model definitions (for table existence only) ─────────────


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
    """Delete only seeded records from the database."""
    with app.app_context():
        # Ensure schema is compatible (adds ``seeded`` column if missing).
        ensure_seeded_columns()

        # Delete bookings first (foreign-key dependency) using raw SQL.
        result = db.session.execute(db.text("DELETE FROM booking WHERE seeded = 1"))
        db.session.commit()
        print(f"  Removed {result.rowcount} seeded booking(s).")

        # Delete support requests using raw SQL.
        result = db.session.execute(db.text("DELETE FROM support_request WHERE seeded = 1"))
        db.session.commit()
        print(f"  Removed {result.rowcount} seeded request(s).")

        if not keep_centres:
            result = db.session.execute(db.text("DELETE FROM cooling_centre WHERE seeded = 1"))
            db.session.commit()
            print(f"  Removed {result.rowcount} seeded centre(s).")
        else:
            count_result = db.session.execute(
                db.text("SELECT COUNT(*) FROM cooling_centre WHERE seeded = 0")
            )
            count = count_result.scalar()
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
