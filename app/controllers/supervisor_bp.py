"""Supervisor-only endpoints (US19 AC2/AC4)."""

from flask import Blueprint, jsonify

from app.database import db
from app.models.support_request import SupportRequest
from app.utils.auth import require_supervisor

bp = Blueprint("supervisor", __name__, url_prefix="/api/supervisor")


# ---------------------------------------------------------------------------
# PURGE — delete all support requests (supervisor only).
# ---------------------------------------------------------------------------
@bp.route("/purge", methods=["DELETE"])
@require_supervisor
def supervisor_purge():
    """Delete all support requests — supervisor only (US19 AC2/AC4)."""
    db.session.query(SupportRequest).delete()
    db.session.commit()
    return "", 204
