"""Cooling centres CRUD controller."""

from flask import Blueprint, g, jsonify, request

from app.database import db
from app.models.audit_log import AuditLog
from app.models.cooling_centre import CoolingCentre
from app.utils.auth import require_staff
from app.utils.security import log_security_event, sanitize_input

bp = Blueprint("centres", __name__, url_prefix="/api/centres")


# ---------------------------------------------------------------------------
# CREATE — add a new cooling centre (staff-only).
# ---------------------------------------------------------------------------
@bp.route("", methods=["POST"])
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
        resource_id=record.id,
    )

    db.session.add(audit)

    # Commit the centre and audit record together
    db.session.commit()

    return jsonify(record.to_dict()), 201


# ---------------------------------------------------------------------------
# READ — list all centres (public).
# ---------------------------------------------------------------------------
@bp.route("", methods=["GET"])
def list_centres():
    records = db.session.scalars(
        db.select(CoolingCentre).order_by(CoolingCentre.id)
    ).all()
    return jsonify([record.to_dict() for record in records])


# ---------------------------------------------------------------------------
# READ — one centre by ID (public).
# ---------------------------------------------------------------------------
@bp.route("/<int:centre_id>", methods=["GET"])
def get_centre(centre_id):
    record = db.session.get(CoolingCentre, centre_id)
    if record is None:
        return jsonify({"error": "Centre not found"}), 404
    return jsonify(record.to_dict())
