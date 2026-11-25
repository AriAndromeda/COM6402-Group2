"""Heat Shield – COM6402 Sprint 1 starter (ONE FILE).

Learning focus: Flask routes, JSON, SQLAlchemy and simple CRUD.
Support Requests, Cooling Centres and Bookings (US04c happy path).

Install (in a virtual environment):
    python -m pip install flask flask-sqlalchemy
Run:
    python app.py
Try:
    http://127.0.0.1:5000/api/health
    http://127.0.0.1:5000/api/requests
    http://127.0.0.1:5000/api/centres
    http://127.0.0.1:5000/api/bookings

This is a TEACHING EXAMPLE, not a finished Heat Shield application.
There is no authentication: run locally only, using fictional data.
"""

import os

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import update

# 1. Set up Flask and the SQLite database.
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///heatshield.db"
db = SQLAlchemy(app)


# Allowed values for enumerated fields (US04a validation).
ALLOWED_PRIORITIES = ("low", "medium", "high", "critical")
ALLOWED_STATUSES = ("new", "in progress", "completed")
ALLOWED_CATEGORIES = ("welfare", "cooling", "practical-assistance", "medical")


# Field length limits (mirrors model columns for client-side validation).
MAX_DESCRIPTION_LENGTH = 500
MAX_AREA_LENGTH = 80

# Mapping of enum fields to their allowed values — single source of truth.
ENUM_FIELDS = {
    "category": ALLOWED_CATEGORIES,
    "priority": ALLOWED_PRIORITIES,
    "status": ALLOWED_STATUSES,
}


# 2. MODELS: Python classes representing database tables.
class SupportRequest(db.Model):
    """A support request for the Heat Shield cooling-centres service.

    The ``area`` field is stored as provided (original casing preserved).
    Filter queries normalise area to lowercase so lookups are case-insensitive
    (e.g. ``?area=Bolton`` matches a record stored as "Bolton").
    """

    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    area = db.Column(db.String(80), nullable=False)
    priority = db.Column(db.String(20), nullable=False, default="medium")
    status = db.Column(db.String(20), nullable=False, default="new")

    def to_dict(self):
        """Turn a database object into JSON-friendly data."""
        return {
            "id": self.id,
            "description": self.description,
            "category": self.category,
            "area": self.area,
            "priority": self.priority,
            "status": self.status,
        }


class CoolingCentre(db.Model):
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
            "name": self.name,
            "area": self.area,
            "capacity": self.capacity,
            "spaces_available": self.spaces_available,
            "opening_hours": self.opening_hours,
            "status": self.status,
        }


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("support_request.id"), nullable=False)
    centre_id = db.Column(db.Integer, db.ForeignKey("cooling_centre.id"), nullable=False)
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


# 3. HEALTH CHECK: a simple way to check whether Flask is running.
@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


# 4. READ: all requests, optionally filtered by a known field.
@app.get("/api/requests")
def list_requests():
    query = db.select(SupportRequest)

    # Example: GET /api/requests?status=new&area=Bolton
    for field in ("category", "area", "priority", "status"):
        value = request.args.get(field)
        if value:
            # Area filter is case-insensitive (records stored as-is).
            if field == "area":
                query = query.where(
                    db.func.lower(getattr(SupportRequest, field)) == value.lower()
                )
            else:
                query = query.where(getattr(SupportRequest, field) == value)

    records = db.session.scalars(query.order_by(SupportRequest.id)).all()
    return jsonify([record.to_dict() for record in records])


# 5. READ: one request by its ID, or return a 404 error.
@app.get("/api/requests/<int:request_id>")
def get_request(request_id):
    record = db.session.get(SupportRequest, request_id)
    if record is None:
        return jsonify({"error": "Request not found"}), 404
    return jsonify(record.to_dict())


# Helper: validate an enumerated field against its allowed values.
def _validate_enum(value, field_name, allowed):
    """Return (cleaned_value, error_msg)."""
    if not isinstance(value, str) or not value.strip():
        return None, f"{field_name} is required"
    cleaned = value.strip().lower()
    if cleaned not in allowed:
        return None, (f"{field_name} must be one of: " + ", ".join(sorted(allowed)))
    return cleaned, None


# 6. CREATE: receive JSON, check required fields, and save a new row.
@app.post("/api/requests")
def create_request():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send a JSON object"}), 400

    # US04a: required fields must be present and non-empty.
    required = ("description", "category", "area")
    for field in required:
        val = data.get(field) if isinstance(data, dict) else None
        if not isinstance(val, str) or not val.strip():
            return jsonify({"error": f"{field} is required"}), 400

    # Validate category against allowed values.
    cat_clean, err = _validate_enum(data["category"], "category", ALLOWED_CATEGORIES)
    if err:
        return jsonify({"error": err}), 400

    # Validate optional enumerated fields with sensible defaults.
    priority_raw = data.get("priority")
    status_raw = data.get("status")

    if isinstance(priority_raw, str) and priority_raw.strip():
        priority_clean, err = _validate_enum(
            priority_raw, "priority", ALLOWED_PRIORITIES
        )
        if err:
            return jsonify({"error": err}), 400
    else:
        priority_clean = "medium"

    if isinstance(status_raw, str) and status_raw.strip():
        status_clean, err = _validate_enum(status_raw, "status", ALLOWED_STATUSES)
        if err:
            return jsonify({"error": err}), 400
    else:
        status_clean = "new"

    # Issue #2: enforce column length limits at the API boundary.
    desc_raw = data["description"].strip()
    if len(desc_raw) > MAX_DESCRIPTION_LENGTH:
        return jsonify(
            {
                "error": f"description must be {MAX_DESCRIPTION_LENGTH} characters or fewer"
            }
        ), 400

    area_raw = data["area"].strip()
    if len(area_raw) > MAX_AREA_LENGTH:
        return jsonify(
            {"error": f"area must be {MAX_AREA_LENGTH} characters or fewer"}
        ), 400

    record = SupportRequest(
        description=desc_raw,
        category=cat_clean,
        area=area_raw,
        priority=priority_clean,
        status=status_clean,
    )
    db.session.add(record)
    db.session.commit()  # Save changes to SQLite.
    return jsonify(record.to_dict()), 201


# 7. UPDATE: PATCH only the fields supplied in the request.
@app.patch("/api/requests/<int:request_id>")
def update_request(request_id):
    record = db.session.get(SupportRequest, request_id)
    if record is None:
        return jsonify({"error": "Request not found"}), 404

    data = request.get_json(silent=True)
    allowed_fields = ("description", "category", "area", "priority", "status")
    if not isinstance(data, dict) or not data:
        return jsonify({"error": "Send fields to update as JSON"}), 400

    # Phase 1 — validate ALL fields before mutating anything.
    cleaned_values = {}
    for field_name, value in data.items():
        if field_name not in allowed_fields:
            return jsonify({"error": f"Cannot update {field_name}"}), 400

        # Enum fields use the shared mapping (DRY — Issue #4).
        if field_name in ENUM_FIELDS:
            cleaned, err = _validate_enum(value, field_name, ENUM_FIELDS[field_name])
            if err:
                return jsonify({"error": err}), 400
            cleaned_values[field_name] = cleaned

        elif field_name == "description":
            desc_raw = value.strip() if isinstance(value, str) else value
            if not isinstance(desc_raw, str) or not desc_raw:
                return jsonify({"error": f"description is required"}), 400
            if len(desc_raw) > MAX_DESCRIPTION_LENGTH:
                return jsonify(
                    {
                        "error": f"description must be {MAX_DESCRIPTION_LENGTH} characters or fewer"
                    }
                ), 400
            cleaned_values[field_name] = desc_raw

        elif field_name == "area":
            area_raw = value.strip() if isinstance(value, str) else value
            if not isinstance(area_raw, str) or not area_raw:
                return jsonify({"error": f"area is required"}), 400
            if len(area_raw) > MAX_AREA_LENGTH:
                return jsonify(
                    {"error": f"area must be {MAX_AREA_LENGTH} characters or fewer"}
                ), 400
            cleaned_values[field_name] = area_raw

    # Phase 2 — apply all validated changes at once (Issue #1).
    for field_name, value in cleaned_values.items():
        setattr(record, field_name, value)

    db.session.commit()
    return jsonify(record.to_dict())


# 8. DELETE: included to illustrate CRUD; not necessarily appropriate
# for real support records, where cancellation/retention may be preferable.
@app.delete("/api/requests/<int:request_id>")
def delete_request(request_id):
    record = db.session.get(SupportRequest, request_id)
    if record is None:
        return jsonify({"error": "Request not found"}), 404
    db.session.delete(record)
    db.session.commit()
    return "", 204  # Success: no response body.


# 9. COOLING CENTRES: create and retrieve (needed to book spaces).
@app.post("/api/centres")
def create_centre():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send a JSON object"}), 400

    for field in ("name", "area"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            return jsonify({"error": f"{field} is required"}), 400

    capacity = data.get("capacity")
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
        return jsonify({"error": "capacity must be a positive integer"}), 400

    opening_hours = data.get("opening_hours", "")
    if opening_hours is None:
        opening_hours = ""
    if not isinstance(opening_hours, str):
        return jsonify({"error": "opening_hours must be text"}), 400

    status = data.get("status", "open")
    if not isinstance(status, str) or not status.strip():
        return jsonify({"error": "status must be text"}), 400

    record = CoolingCentre(
        name=data["name"].strip(),
        area=data["area"].strip(),
        capacity=capacity,
        spaces_available=capacity,
        opening_hours=opening_hours.strip(),
        status=status.strip().lower(),
    )
    db.session.add(record)
    db.session.commit()
    return jsonify(record.to_dict()), 201


@app.get("/api/centres")
def list_centres():
    records = db.session.scalars(
        db.select(CoolingCentre).order_by(CoolingCentre.id)
    ).all()
    return jsonify([record.to_dict() for record in records])


@app.get("/api/centres/<int:centre_id>")
def get_centre(centre_id):
    record = db.session.get(CoolingCentre, centre_id)
    if record is None:
        return jsonify({"error": "Centre not found"}), 404
    return jsonify(record.to_dict())


# 10. BOOKINGS (US04c happy path): reserve spaces and reduce availability.
@app.post("/api/bookings")
def create_booking():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send a JSON object"}), 400

    request_id = data.get("request_id")
    centre_id = data.get("centre_id")
    if not isinstance(request_id, int) or isinstance(request_id, bool):
        return jsonify({"error": "request_id is required"}), 400
    if not isinstance(centre_id, int) or isinstance(centre_id, bool):
        return jsonify({"error": "centre_id is required"}), 400

    for field in ("booking_date", "booking_time"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            return jsonify({"error": f"{field} is required"}), 400

    spaces_required = data.get("spaces_required")
    if (
        not isinstance(spaces_required, int)
        or isinstance(spaces_required, bool)
        or spaces_required < 1
    ):
        return jsonify({"error": "spaces_required must be a positive integer"}), 400

    support_request = db.session.get(SupportRequest, request_id)
    if support_request is None:
        return jsonify({"error": "Request not found"}), 404

    centre = db.session.get(CoolingCentre, centre_id)
    if centre is None:
        return jsonify({"error": "Centre not found"}), 404

    # Happy-path booking: centre must be open with enough remaining spaces.
    # US08d: Atomically check and reserve available capacity.
    # A conditional UPDATE prevents competing requests from
    # reserving the same remaining spaces.
    try:
        result = db.session.execute(
            update(CoolingCentre)
            .where(
                CoolingCentre.id == centre_id,
                db.func.lower(CoolingCentre.status) == "open",
                CoolingCentre.spaces_available >= spaces_required,
            )
            .values(
                spaces_available=(
                    CoolingCentre.spaces_available - spaces_required
                )
            )
        )

        if result.rowcount != 1:
            db.session.rollback()

            # Return an appropriate error without reserving spaces.
            db.session.refresh(centre)

            if centre.status.lower() != "open":
                return jsonify({"error": "Centre is closed"}), 409

            return jsonify({"error": "Not enough spaces available"}), 409

        booking = Booking(
            request_id=request_id,
            centre_id=centre_id,
            booking_date=data["booking_date"].strip(),
            booking_time=data["booking_time"].strip(),
            spaces_required=spaces_required,
            status="confirmed",
        )

        db.session.add(booking)

        # Capacity reduction and booking creation are committed together.
        db.session.commit()

        return jsonify(booking.to_dict()), 201

    except Exception:
        db.session.rollback()
        raise



@app.get("/api/bookings/<int:booking_id>")
def get_booking(booking_id):
    record = db.session.get(Booking, booking_id)
    if record is None:
        return jsonify({"error": "Booking not found"}), 404
    return jsonify(record.to_dict())


def get_port():
    """Return the configured PORT, defaulting to 5000."""
    raw_port = os.getenv("PORT", "5000")
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise ValueError("PORT must be an integer") from exc

    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535")

    return port


if __name__ == "__main__":
    # Create the table if it does not already exist.
    # Later: consider proper database migrations when changing the schema.
    with app.app_context():
        db.create_all()

    # Flask's debug server is only suitable for LOCAL development.
    app.run(debug=True, host="127.0.0.1", port=get_port())
