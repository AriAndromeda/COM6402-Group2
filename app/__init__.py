"""Heat Shield – COM6402 Sprint 1 starter (MVC refactored).

Learning focus: Flask routes, JSON, SQLAlchemy and simple CRUD.
Support Requests, Cooling Centres and Bookings (US04c happy path).

This package replaces the original single-file app.py with a proper
Model-View-Controller architecture:

    models/      – SQLAlchemy ORM classes (data layer)
    controllers/ – Flask blueprints with route handlers (logic layer)
    utils/       – Security, encryption, auth, validation helpers
    __init__.py  – Application factory + re-exports for test compatibility
"""

import os

from flask import Flask, jsonify

from app.database import create_db, db


def create_app(config_overrides=None):
    """Application factory — creates and configures the Flask app.

    Parameters
    ----------
    config_overrides : dict, optional
        Extra configuration values to apply after defaults.

    Returns
    -------
    Flask
        Configured application instance with all blueprints registered.
    """
    # 1. Create Flask app and attach SQLAlchemy.
    app = Flask(__name__)
    create_db(app)

    if config_overrides:
        app.config.update(config_overrides)

    # US19 AC2: Disable debug mode in production to prevent stack trace exposure.
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.config["PROPAGATE_EXCEPTIONS"] = False  # Hide internal errors from clients.

    # 2. Register blueprint controllers (routes layer).
    from app.controllers import requests_bp, centres_bp, bookings_bp, supervisor_bp

    app.register_blueprint(requests_bp)
    app.register_blueprint(centres_bp)
    app.register_blueprint(bookings_bp)
    app.register_blueprint(supervisor_bp)

    # 3. Health check endpoint (no blueprint needed for such a simple route).
    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    # 4. Global error handlers (US19 AC2: prevent exposing system internals).
    from app.utils.security import log_security_event

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

    return app


# ---------------------------------------------------------------------------
# Re-export symbols that tests and the CLI expect at module level.
# ---------------------------------------------------------------------------
from app.database import db          # noqa: E402 – must come after create_app()
from app.models import (             # noqa: E402
    SupportRequest,
    CoolingCentre,
    Booking,
    StaffUser,
    AuditLog,
    SecurityAuditLog,
)

# Build the default application so ``python app.py`` and tests work without
# explicitly calling create_app().
app = create_app()


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
    with app.app_context():
        db.create_all()

    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug_mode, host="127.0.0.1", port=get_port())
