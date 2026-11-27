"""Requests CRUD controller (US04c)."""

from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request

from app.database import db
from app.models.audit_log import AuditLog
from app.models.support_request import SupportRequest
from app.utils.auth import require_staff
from app.utils.encryption import encrypt_field
from app.utils.security import log_security_event, sanitize_input
from app.utils.validation import (
    ALLOWED_CATEGORIES,
    ALLOWED_PRIORITIES,
    ALLOWED_STATUSES,
    ENUM_FIELDS,
    MAX_AREA_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    validate_enum,
)

bp = Blueprint("requests", __name__, url_prefix="/api/requests")


# ---------------------------------------------------------------------------
# READ — list all requests (public, optionally filtered).
# ---------------------------------------------------------------------------
@bp.route("", methods=["GET"])
def list_requests():
    query = db.select(SupportRequest)

    # Example: GET /api/requests?status=new&area=Bolton
    for field in ("category", "area", "priority", "status"):
        value = request.args.get(field)
        if value:
            if field == "area":
                query = query.where(
                    db.func.lower(getattr(SupportRequest, field)) == value.lower()
                )
            else:
                query = query.where(getattr(SupportRequest, field) == value)

    records = db.session.scalars(
        query.order_by(SupportRequest.id)
    ).all()
    return jsonify([record.to_dict() for record in records])


# ---------------------------------------------------------------------------
# READ — one request by ID.
# ---------------------------------------------------------------------------
@bp.route("/<int:request_id>", methods=["GET"])
def get_request(request_id):
    record = db.session.get(SupportRequest, request_id)
    if record is None:
        return jsonify({"error": "Request not found"}), 404
    return jsonify(record.to_dict())


# ---------------------------------------------------------------------------
# CREATE — receive JSON, validate, and save.
# ---------------------------------------------------------------------------
@bp.route("", methods=["POST"])
def create_request():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send a JSON object"}), 400

    # US04a: required fields must be present and non-empty.
    for field in ("description", "category", "area"):
        val = data.get(field) if isinstance(data, dict) else None
        if not isinstance(val, str) or not val.strip():
            log_security_event("REJECTED_INPUT", f"Missing required field: {field}")
            return jsonify({"error": f"{field} is required"}), 400

    # Validate category against allowed values.
    cat_clean, err = validate_enum(data["category"], "category", ALLOWED_CATEGORIES)
    if err:
        log_security_event("REJECTED_INPUT", "Invalid category value")
        return jsonify({"error": err}), 400

    # Validate optional enumerated fields with sensible defaults.
    priority_raw = data.get("priority")
    status_raw = data.get("status")

    if isinstance(priority_raw, str) and priority_raw.strip():
        priority_clean, err = validate_enum(
            priority_raw, "priority", ALLOWED_PRIORITIES
        )
        if err:
            log_security_event("REJECTED_INPUT", "Invalid priority value")
            return jsonify({"error": err}), 400
    else:
        priority_clean = "medium"

    if isinstance(status_raw, str) and status_raw.strip():
        status_clean, err = validate_enum(status_raw, "status", ALLOWED_STATUSES)
        if err:
            log_security_event("REJECTED_INPUT", "Invalid status value")
            return jsonify({"error": err}), 400
    else:
        status_clean = "new"

    # Issue #2: enforce column length limits at the API boundary.
    desc_raw = data["description"].strip()
    if len(desc_raw) > MAX_DESCRIPTION_LENGTH:
        log_security_event(
            "REJECTED_INPUT", f"description exceeds {MAX_DESCRIPTION_LENGTH} chars"
        )
        return jsonify(
            {"error": f"description must be {MAX_DESCRIPTION_LENGTH} characters or fewer"}
        ), 400

    area_raw = data["area"].strip()
    if len(area_raw) > MAX_AREA_LENGTH:
        log_security_event("REJECTED_INPUT", f"area exceeds {MAX_AREA_LENGTH} chars")
        return jsonify(
            {"error": f"area must be {MAX_AREA_LENGTH} characters or fewer"}
        ), 400

    # US19 AC3: Encrypt sensitive data at rest.
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


# ---------------------------------------------------------------------------
# UPDATE — PATCH only the fields supplied in the request (staff-only).
# ---------------------------------------------------------------------------
@bp.route("/<int:request_id>", methods=["PATCH"])
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
            cleaned, err = validate_enum(value, field_name, ENUM_FIELDS[field_name])
            if err:
                log_security_event("REJECTED_INPUT", f"Invalid {field_name} value")
                return jsonify({"error": err}), 400
            cleaned_values[field_name] = cleaned

        elif field_name == "description":
            desc_raw = value.strip() if isinstance(value, str) else value
            if not isinstance(desc_raw, str) or not desc_raw:
                log_security_event("REJECTED_INPUT", "Empty description")
                return jsonify({"error": "description is required"}), 400
            if len(desc_raw) > MAX_DESCRIPTION_LENGTH:
                log_security_event(
                    "REJECTED_INPUT", f"description exceeds {MAX_DESCRIPTION_LENGTH} chars"
                )
                return jsonify(
                    {"error": f"description must be {MAX_DESCRIPTION_LENGTH} characters or fewer"}
                ), 400
            cleaned_values[field_name] = encrypt_field(desc_raw)

        elif field_name == "area":
            area_raw = value.strip() if isinstance(value, str) else value
            if not isinstance(area_raw, str) or not area_raw:
                log_security_event("REJECTED_INPUT", "Empty area")
                return jsonify({"error": "area is required"}), 400
            if len(area_raw) > MAX_AREA_LENGTH:
                log_security_event(
                    "REJECTED_INPUT", f"area exceeds {MAX_AREA_LENGTH} chars"
                )
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


# ---------------------------------------------------------------------------
# DELETE — remove a request (staff-only).
# ---------------------------------------------------------------------------
@bp.route("/<int:request_id>", methods=["DELETE"])
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
        resource_id=deleted_request_id,
    )

    db.session.add(audit)
    db.session.commit()

    return "", 204  # Success: no response body.
