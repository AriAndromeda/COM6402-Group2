"""Bookings controller (US04c happy path)."""

from flask import Blueprint, g, jsonify, request
from sqlalchemy import update

from app.database import db
from app.models.audit_log import AuditLog
from app.models.booking import Booking
from app.utils.auth import require_staff
from app.utils.security import log_security_event

bp = Blueprint("bookings", __name__, url_prefix="/api/bookings")


# ---------------------------------------------------------------------------
# CREATE — reserve spaces and reduce availability (staff-only).
# ---------------------------------------------------------------------------
@bp.route("", methods=["POST"])
@require_staff("staff", "supervisor")
def create_booking():
    from app.models.support_request import SupportRequest
    from app.models.cooling_centre import CoolingCentre

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
    try:
        result = db.session.execute(
            update(CoolingCentre)
            .where(
                CoolingCentre.id == centre_id,
                db.func.lower(CoolingCentre.status) == "open",
                CoolingCentre.spaces_available >= spaces_required,
            )
            .values(
                spaces_available=(CoolingCentre.spaces_available - spaces_required)
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


# ---------------------------------------------------------------------------
# READ — one booking by ID (public).
# ---------------------------------------------------------------------------
@bp.route("/<int:booking_id>", methods=["GET"])
def get_booking(booking_id):
    record = db.session.get(Booking, booking_id)
    if record is None:
        return jsonify({"error": "Booking not found"}), 404
    return jsonify(record.to_dict())
