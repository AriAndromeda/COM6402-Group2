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

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy

# 1. Set up Flask and the SQLite database.
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///heatshield.db"
db = SQLAlchemy(app)


# 2. MODELS: Python classes representing database tables.
class SupportRequest(db.Model):
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


# 6. CREATE: receive JSON, check required fields, and save a new row.
@app.post("/api/requests")
def create_request():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send a JSON object"}), 400

    required = ("description", "category", "area")
    for field in required:
        if not isinstance(data.get(field), str) or not data[field].strip():
            return jsonify({"error": f"{field} is required"}), 400

    # This simple example accepts two optional fields.
    # Students should improve validation (allowed values, lengths, etc.).
    for field in ("priority", "status"):
        if field in data and (
            not isinstance(data[field], str) or not data[field].strip()
        ):
            return jsonify({"error": f"{field} must be text"}), 400

    record = SupportRequest(
        description=data["description"].strip(),
        category=data["category"].strip(),
        area=data["area"].strip(),
        priority=data.get("priority", "medium").strip(),
        status=data.get("status", "new").strip(),
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
    allowed = ("description", "category", "area", "priority", "status")
    if not isinstance(data, dict) or not data:
        return jsonify({"error": "Send fields to update as JSON"}), 400

    for field, value in data.items():
        if field not in allowed:
            return jsonify({"error": f"Cannot update {field}"}), 400
        if not isinstance(value, str) or not value.strip():
            return jsonify({"error": f"{field} must contain text"}), 400
        setattr(record, field, value.strip())

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
    if centre.spaces_available < spaces_required:
        return jsonify({"error": "Not enough spaces available"}), 409
    if centre.status.lower() != "open":
        return jsonify({"error": "Centre is closed"}), 409

    booking = Booking(
        request_id=request_id,
        centre_id=centre_id,
        booking_date=data["booking_date"].strip(),
        booking_time=data["booking_time"].strip(),
        spaces_required=spaces_required,
        status="confirmed",
    )
    centre.spaces_available -= spaces_required
    db.session.add(booking)
    db.session.commit()
    return jsonify(booking.to_dict()), 201


@app.get("/api/bookings/<int:booking_id>")
def get_booking(booking_id):
    record = db.session.get(Booking, booking_id)
    if record is None:
        return jsonify({"error": "Booking not found"}), 404
    return jsonify(record.to_dict())


if __name__ == "__main__":
    # Create the table if it does not already exist.
    # Later: consider proper database migrations when changing the schema.
    with app.app_context():
        db.create_all()

    # Flask's debug server is only suitable for LOCAL development.
    app.run(debug=True, host="127.0.0.1", port=5000)
