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

This is a teaching prototype, not a production-ready application.
US06 provides Bearer-token authentication and role-based access control
for protected write operations, with audit logging of successful changes.
Some endpoints remain public. Run locally using fictional data only.

US19 adds security testing: input sanitisation, generic error messages,
encryption at rest (configurable via HEATSHIELD_ENCRYPTION_KEY), and
security event logging for failed auth, rejected inputs, and access denials.
"""

import html
import hashlib
import logging
import os
import secrets
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, g, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import update

from llm_adapter import get_adapter
from triage import generate_triage_draft

# US19: Security configuration and logging setup.
logging.basicConfig(level=logging.INFO)
security_logger = logging.getLogger("heatshield.security")
security_handler = logging.FileHandler("security_events.log")
security_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)
security_logger.addHandler(security_handler)
security_logger.setLevel(logging.INFO)


def log_security_event(event_type, details="", ip_address=None):
    """Log a security-relevant event for audit purposes (US19 AC4).

    Writes to the file logger AND persists a row in SecurityAuditLog so that
    both mechanisms are available at rest.
    """
    if ip_address is None:
        ip_address = request.remote_addr if request else "unknown"
    message = f"[{event_type}] IP={ip_address} {details}"
    security_logger.warning(message)

    # Persist to the database audit table so rows survive a log-rotation.
    try:
        row = SecurityAuditLog(
            event_type=event_type,
            ip_address=ip_address,
            details=details,
            timestamp=datetime.now(timezone.utc),
        )
        db.session.add(row)
        db.session.commit()
    except Exception:
        # If the DB is unavailable fall back to file-only logging.
        db.session.rollback()


def sanitize_input(value):
    """Sanitise user input for XSS/injection prevention (US19 AC1).

    Returns a cleaned copy; does NOT HTML-escape — that happens at output time
    via contextual encoding in model ``to_dict()``, avoiding double-encoding.
    """
    if isinstance(value, str):
        return value.strip()
    return value


def encode_for_output(value):
    """Contextual HTML-encoding for safe display (US19 AC1).

    Applied at output time so the original data is preserved in storage and
    only encoded when rendered — prevents double-encoding and preserves
    legitimate characters such as parentheses, quotes, and angle brackets.
    """
    if isinstance(value, str):
        return html.escape(value)
    return value


# US19 AC3: Encryption at rest for sensitive data.
_ENCRYPTION_KEY = os.environ.get("HEATSHIELD_ENCRYPTION_KEY", None)

if _ENCRYPTION_KEY is not None:
    from cryptography.fernet import Fernet
    _fernet = Fernet(_ENCRYPTION_KEY.encode())

    def encrypt_field(plaintext):
        """Encrypt a string field before storing in the database."""
        if plaintext is None:
            return None
        return _fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt_field(ciphertext):
        """Decrypt an encrypted field after reading from the database."""
        if ciphertext is None:
            return None
        try:
            return _fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except Exception:
            # Decryption failed — return raw value to avoid leaking errors.
            return "[encrypted]"
else:
    # No encryption key configured; store data as-is (development mode).
    def encrypt_field(plaintext):
        """No-op when no encryption key is set."""
        return plaintext

    def decrypt_field(ciphertext):
        """No-op when no encryption key is set."""
        return ciphertext

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
# US13: keep LLM prompts bounded (fictional case text only).
MAX_LLM_PROMPT_LENGTH = 2000

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
        # Decrypt first (if encryption is enabled), then encode for safe display.
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
            "name": encode_for_output(self.name),
            "area": encode_for_output(self.area),
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

    # US06 - Staff identity and audit models
class StaffUser(db.Model):
    """Store staff identities and their access roles."""

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(
        db.String(80),
        unique=True,
        nullable=False
    )

    role = db.Column(
        db.String(20),
        nullable=False,
        default="staff"
    )

    token_hash = db.Column(
        db.String(64),
        unique=True,
        nullable=False
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True
    )


class AuditLog(db.Model):
    """Record successful actions performed by staff."""

    id = db.Column(db.Integer, primary_key=True)

    staff_user_id = db.Column(
        db.Integer,
        db.ForeignKey("staff_user.id"),
        nullable=False
    )

    action = db.Column(
        db.String(100),
        nullable=False
    )

    resource_type = db.Column(
        db.String(50),
        nullable=False
    )

    resource_id = db.Column(
        db.Integer,
        nullable=False
    )

    timestamp = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self):
        return {
            "id": self.id,
            "staff_user_id": self.staff_user_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "timestamp": self.timestamp.isoformat()
        }


# US19: Security audit log for failed auth, rejected inputs, access denials.
class SecurityAuditLog(db.Model):
    """Record security-relevant events for audit purposes (US19 AC4)."""

    id = db.Column(db.Integer, primary_key=True)

    event_type = db.Column(
        db.String(50),
        nullable=False
    )

    ip_address = db.Column(
        db.String(45),
        nullable=True
    )

    details = db.Column(
        db.Text,
        nullable=True
    )

    timestamp = db.Column(db.DateTime(timezone=True), nullable=False)


    # US06 - Staff authentication and authorisation

def require_staff(*allowed_roles):
    """Restrict an endpoint to authenticated, authorised staff."""

    def decorator(view_function):
        @wraps(view_function)
        def wrapper(*args, **kwargs):

            # Read the Bearer token from the request header
            authorization = request.headers.get("Authorization", "")
            parts = authorization.split()

            if (
                len(parts) != 2
                or parts[0].lower() != "bearer"
                or not parts[1]
            ):
                # US19 AC4: Log failed authentication attempts.
                log_security_event(
                    "AUTH_FAILED",
                    "Missing or malformed Bearer token",
                )
                return jsonify({
                    "error": "Authentication required"
                }), 401

            # Hash the supplied token before database lookup
            token_hash = hashlib.sha256(
                parts[1].encode("utf-8")
            ).hexdigest()

            staff = db.session.scalar(
                db.select(StaffUser).where(
                    StaffUser.token_hash == token_hash
                )
            )

            # Reject unknown or inactive staff accounts
            if staff is None or not staff.is_active:
                # US19 AC4: Log failed authentication attempts.
                log_security_event(
                    "AUTH_FAILED",
                    f"Invalid or inactive credentials (token hash={token_hash[:8]}...)",
                )
                return jsonify({
                    "error": "Invalid or inactive credentials"
                }), 401

            # Check whether the staff role is authorised
            if staff.role not in allowed_roles:
                # US19 AC4: Log access denied events.
                log_security_event(
                    "ACCESS_DENIED",
                    f"Insufficient permissions for role={staff.role}",
                )
                return jsonify({
                    "error": "Insufficient permissions"
                }), 403

            # Make the authenticated identity available to the route
            g.current_staff = staff

            return view_function(*args, **kwargs)

        return wrapper

    return decorator


# US19 AC2/AC4: Supervisor-only access for sensitive operations.
def require_supervisor(view_function):
    """Restrict an endpoint to supervisor role only (US19 AC2/AC4)."""
    return require_staff("supervisor")(view_function)


def generate_staff_token():
    """Generate a cryptographically secure staff access token."""
    return secrets.token_urlsafe(32)


def provision_staff(username, role="staff"):
    """Provision a staff account without exposing a public registration API."""

    # Validate the username
    if not isinstance(username, str) or not username.strip():
        raise ValueError("A valid username is required")

    username = username.strip()

    if len(username) > 80:
        raise ValueError("Username must not exceed 80 characters")

    # Restrict accounts to approved roles
    if role not in ("staff", "supervisor"):
        raise ValueError("Invalid staff role")

    # Prevent duplicate staff accounts
    existing_staff = db.session.scalar(
        db.select(StaffUser).where(
            StaffUser.username == username
        )
    )

    if existing_staff is not None:
        raise ValueError("Staff username already exists")

    # Generate a cryptographically secure access token
    token = generate_staff_token()

    # Store only the token hash
    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    staff = StaffUser(
        username=username,
        role=role,
        token_hash=token_hash,
        is_active=True
    )

    db.session.add(staff)
    db.session.commit()

    # Return the token once to the trusted provisioning caller
    return token



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
            # US19 AC4: Log rejected input attempts.
            log_security_event("REJECTED_INPUT", f"Missing required field: {field}")
            return jsonify({"error": f"{field} is required"}), 400

    # Validate category against allowed values.
    cat_clean, err = _validate_enum(data["category"], "category", ALLOWED_CATEGORIES)
    if err:
        # US19 AC2: Generic error message (no system internals exposed).
        log_security_event("REJECTED_INPUT", f"Invalid category value")
        return jsonify({"error": err}), 400

    # Validate optional enumerated fields with sensible defaults.
    priority_raw = data.get("priority")
    status_raw = data.get("status")

    if isinstance(priority_raw, str) and priority_raw.strip():
        priority_clean, err = _validate_enum(
            priority_raw, "priority", ALLOWED_PRIORITIES
        )
        if err:
            log_security_event("REJECTED_INPUT", f"Invalid priority value")
            return jsonify({"error": err}), 400
    else:
        priority_clean = "medium"

    if isinstance(status_raw, str) and status_raw.strip():
        status_clean, err = _validate_enum(status_raw, "status", ALLOWED_STATUSES)
        if err:
            log_security_event("REJECTED_INPUT", f"Invalid status value")
            return jsonify({"error": err}), 400
    else:
        status_clean = "new"

    # Issue #2: enforce column length limits at the API boundary.
    desc_raw = data["description"].strip()
    if len(desc_raw) > MAX_DESCRIPTION_LENGTH:
        log_security_event("REJECTED_INPUT", f"description exceeds {MAX_DESCRIPTION_LENGTH} chars")
        return jsonify(
            {
                "error": f"description must be {MAX_DESCRIPTION_LENGTH} characters or fewer"
            }
        ), 400

    area_raw = data["area"].strip()
    if len(area_raw) > MAX_AREA_LENGTH:
        log_security_event("REJECTED_INPUT", f"area exceeds {MAX_AREA_LENGTH} chars")
        return jsonify(
            {"error": f"area must be {MAX_AREA_LENGTH} characters or fewer"}
        ), 400

    # US19 AC3: Encrypt sensitive data at rest (encrypt raw value first).
    # US19 AC1: Contextual output encoding applied in to_dict() — no pre-escaping.
    record = SupportRequest(
        description=encrypt_field(desc_raw),
        category=cat_clean,
        area=sanitize_input(area_raw),
        priority=priority_clean,
        status=status_clean,
    )
    db.session.add(record)
    db.session.commit()  # Save changes to SQLite.
    return jsonify(record.to_dict()), 201


# 7. UPDATE: PATCH only the fields supplied in the request.
@app.patch("/api/requests/<int:request_id>")
@require_staff("staff", "supervisor")
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
            log_security_event("REJECTED_INPUT", f"Invalid update field: {field_name}")
            return jsonify({"error": f"Cannot update {field_name}"}), 400

        # Enum fields use the shared mapping (DRY — Issue #4).
        if field_name in ENUM_FIELDS:
            cleaned, err = _validate_enum(value, field_name, ENUM_FIELDS[field_name])
            if err:
                log_security_event("REJECTED_INPUT", f"Invalid {field_name} value")
                return jsonify({"error": err}), 400
            cleaned_values[field_name] = cleaned

        elif field_name == "description":
            desc_raw = value.strip() if isinstance(value, str) else value
            if not isinstance(desc_raw, str) or not desc_raw:
                log_security_event("REJECTED_INPUT", f"Empty description")
                return jsonify({"error": f"description is required"}), 400
            if len(desc_raw) > MAX_DESCRIPTION_LENGTH:
                log_security_event("REJECTED_INPUT", f"description exceeds {MAX_DESCRIPTION_LENGTH} chars")
                return jsonify(
                    {
                        "error": f"description must be {MAX_DESCRIPTION_LENGTH} characters or fewer"
                    }
                ), 400
            # US19 AC3: Encrypt raw value before storing.
            # US19 AC1: Contextual output encoding applied in to_dict().
            cleaned_values[field_name] = encrypt_field(desc_raw)

        elif field_name == "area":
            area_raw = value.strip() if isinstance(value, str) else value
            if not isinstance(area_raw, str) or not area_raw:
                log_security_event("REJECTED_INPUT", f"Empty area")
                return jsonify({"error": f"area is required"}), 400
            if len(area_raw) > MAX_AREA_LENGTH:
                log_security_event("REJECTED_INPUT", f"area exceeds {MAX_AREA_LENGTH} chars")
                return jsonify(
                    {"error": f"area must be {MAX_AREA_LENGTH} characters or fewer"}
                ), 400
            cleaned_values[field_name] = sanitize_input(area_raw)


    # Phase 2: Apply all validated changes.
    for field_name, value in cleaned_values.items():
        setattr(record, field_name, value)

    # Keep the modification timestamp accurate.
    record.updated_at = datetime.now(timezone.utc)

    # US06: Record the authorised staff action.
    audit = AuditLog(
        staff_user_id=g.current_staff.id,
        action="update",
        resource_type="support_request",
        resource_id=record.id,
    )

    # Save the request update and audit record together.
    db.session.add(audit)
    db.session.commit()

    return jsonify(record.to_dict())



# 8. DELETE: included to illustrate CRUD; not necessarily appropriate
# for real support records, where cancellation/retention may be preferable.
@app.delete("/api/requests/<int:request_id>")
@require_staff("staff", "supervisor")
def delete_request(request_id):
    record = db.session.get(SupportRequest, request_id)
    if record is None:
        return jsonify({"error": "Request not found"}), 404

    # Preserve the request ID before deletion
    deleted_request_id = record.id

    # Delete the support request
    db.session.delete(record)

    # US06: Record which staff member performed the deletion
    audit = AuditLog(
        staff_user_id=g.current_staff.id,
        action="delete",
        resource_type="support_request",
        resource_id=deleted_request_id
    )

    db.session.add(audit)

    # Commit the deletion and audit record together
    db.session.commit()

    return "", 204
 # Success: no response body.


# 9. COOLING CENTRES: create and retrieve (needed to book spaces).
@app.post("/api/centres")
@require_staff("staff", "supervisor")
def create_centre():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send a JSON object"}), 400

    for field in ("name", "area"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            log_security_event("REJECTED_INPUT", f"Missing required centre field: {field}")
            return jsonify({"error": f"{field} is required"}), 400

    capacity = data.get("capacity")
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
        log_security_event("REJECTED_INPUT", "Invalid centre capacity value")
        return jsonify({"error": "capacity must be a positive integer"}), 400

    opening_hours = data.get("opening_hours", "")
    if opening_hours is None:
        opening_hours = ""
    if not isinstance(opening_hours, str):
        log_security_event("REJECTED_INPUT", "Invalid centre opening_hours type")
        return jsonify({"error": "opening_hours must be text"}), 400

    status = data.get("status", "open")
    if not isinstance(status, str) or not status.strip():
        log_security_event("REJECTED_INPUT", "Empty centre status")
        return jsonify({"error": "status must be text"}), 400

    record = CoolingCentre(
        name=sanitize_input(data["name"].strip()),
        area=sanitize_input(data["area"].strip()),
        capacity=capacity,
        spaces_available=capacity,
        opening_hours=opening_hours.strip(),
        status=status.strip().lower(),
    )

    # Stage the cooling centre and obtain its database ID
    db.session.add(record)
    db.session.flush()

    # US06: Record the authorised staff action
    audit = AuditLog(
        staff_user_id=g.current_staff.id,
        action="create",
        resource_type="cooling_centre",
        resource_id=record.id
    )

    db.session.add(audit)

    # Commit the centre and audit record together
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
@require_staff("staff", "supervisor")
def create_booking():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send a JSON object"}), 400

    request_id = data.get("request_id")
    centre_id = data.get("centre_id")
    if not isinstance(request_id, int) or isinstance(request_id, bool):
        log_security_event("REJECTED_INPUT", "Invalid request_id type")
        return jsonify({"error": "request_id is required"}), 400
    if not isinstance(centre_id, int) or isinstance(centre_id, bool):
        log_security_event("REJECTED_INPUT", "Invalid centre_id type")
        return jsonify({"error": "centre_id is required"}), 400

    for field in ("booking_date", "booking_time"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            log_security_event("REJECTED_INPUT", f"Missing booking field: {field}")
            return jsonify({"error": f"{field} is required"}), 400

    spaces_required = data.get("spaces_required")
    if (
        not isinstance(spaces_required, int)
        or isinstance(spaces_required, bool)
        or spaces_required < 1
    ):
        log_security_event("REJECTED_INPUT", "Invalid spaces_required value")
        return jsonify({"error": "spaces_required must be a positive integer"}), 400

    support_request = db.session.get(SupportRequest, request_id)
    if support_request is None:
        # US19 AC2: Generic error — do not confirm whether the ID exists.
        log_security_event("REJECTED_INPUT", f"Booking for non-existent request_id={request_id}")
        return jsonify({"error": "Request not found"}), 404

    centre = db.session.get(CoolingCentre, centre_id)
    if centre is None:
        log_security_event("REJECTED_INPUT", f"Booking for non-existent centre_id={centre_id}")
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

                # Stage the booking and obtain its database ID.
        db.session.add(booking)
        db.session.flush()

        # US06: Record the authorised staff member who created the booking.
        audit = AuditLog(
            staff_user_id=g.current_staff.id,
            action="create",
            resource_type="booking",
            resource_id=booking.id,
        )
        db.session.add(audit)

        # US06 + US08d: Commit capacity, booking and audit atomically.
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


# US13 – LLM adapter status and generate (Sprint 1 attempt).
@app.get("/api/llm/status")
def llm_status():
    """Return non-secret LLM adapter configuration."""
    return jsonify(get_adapter().public_status())


@app.post("/api/llm/generate")
@require_staff("staff", "supervisor")
def llm_generate():
    """Generate advice text via the configured LLM adapter.

    Staff-only. Defaults to mock mode. Live providers read HEATSHIELD_LLM_*
    env vars. Credentials are never included in the JSON response.
    Only fictional case text should be sent to external providers.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send a JSON object"}), 400

    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return jsonify({"error": "prompt is required"}), 400

    cleaned = prompt.strip()
    if len(cleaned) > MAX_LLM_PROMPT_LENGTH:
        return jsonify({
            "error": (
                f"prompt must be {MAX_LLM_PROMPT_LENGTH} characters or fewer"
            )
        }), 400

    result = get_adapter().generate(cleaned)
    return jsonify(result)


# US08a – AI triage draft (staff review only; never auto-applies).
@app.post("/api/requests/<int:request_id>/triage")
@require_staff("staff", "supervisor")
def triage_support_request(request_id):
    """Generate an AI triage *draft* for a support request.

    Returns summary, category, priority, rationale and support option for
    staff review. Does not modify the stored support request.
    """
    record = db.session.get(SupportRequest, request_id)
    if record is None:
        return jsonify({"error": "Support request not found"}), 404

    # Snapshot fields before triage so tests can prove nothing was applied.
    before = {
        "description": record.description,
        "category": record.category,
        "area": record.area,
        "priority": record.priority,
        "status": record.status,
        "updated_at": str(record.updated_at),
    }

    draft_input = {
        "description": decrypt_field(record.description),
        "category": record.category,
        "area": decrypt_field(record.area),
        "priority": record.priority,
        "status": record.status,
    }
    suggestion = generate_triage_draft(draft_input)

    # Re-load and confirm the persisted row is unchanged.
    db.session.refresh(record)
    after = {
        "description": record.description,
        "category": record.category,
        "area": record.area,
        "priority": record.priority,
        "status": record.status,
        "updated_at": str(record.updated_at),
    }
    unchanged = before == after

    # Provider/mode/simulated come from the adapter call inside triage — not
    # from a separate status lookup that could disagree with how the draft
    # was actually produced.
    return jsonify({
        "request_id": record.id,
        "draft": True,
        "status": "pending_review",
        "applied": False,
        "request_unchanged": unchanged,
        "suggestion": {
            key: suggestion[key]
            for key in (
                "summary",
                "category",
                "priority",
                "rationale",
                "support_option",
                "incomplete",
                "missing_fields",
                "draft",
                "status",
                "applied",
            )
            if key in suggestion
        },
        "provider": suggestion.get("provider"),
        "mode": suggestion.get("mode"),
        "model": suggestion.get("model"),
        "simulated": suggestion.get("simulated"),
        "is_live": suggestion.get("is_live"),
        "generation_path": suggestion.get("generation_path"),
        "review_note": (
            "Draft only — staff must review before any category, priority, "
            "or support action is confirmed."
        ),
    })


# US19 AC2/AC4: Supervisor-only endpoint for testing role-based access control.
@app.delete("/api/supervisor/purge")
@require_supervisor
def supervisor_purge():
    """Delete all support requests — supervisor only (US19 AC2/AC4)."""
    db.session.query(SupportRequest).delete()
    db.session.commit()
    return "", 204


# US19 AC2: Global error handlers to prevent exposing system internals.
@app.errorhandler(400)
def bad_request(error):
    log_security_event("ERROR_400", str(error))
    return jsonify({"error": "Bad request"}), 400

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    log_security_event("ERROR_500", str(error))
    return jsonify({"error": "Internal server error"}), 500


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
        # US19 AC4: Ensure security audit tables exist.
        db.create_all()

    # US19 AC2: Disable debug mode in production to prevent stack trace exposure.
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.config["PROPAGATE_EXCEPTIONS"] = False  # Hide internal errors from clients.

    # Flask's debug server is only suitable for LOCAL development.
    app.run(debug=debug_mode, host="127.0.0.1", port=get_port())
