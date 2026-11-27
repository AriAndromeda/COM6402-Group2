"""Heat Shield – CLI entry point (delegates to app package).

Run: python app.py
Tests import from ``app`` (the package): from app import StaffUser, app, db
"""

from app import app  # noqa: F401 – re-exported by the package for test compatibility

if __name__ == "__main__":
    from app import create_app, get_port

    application = create_app()
    debug_mode = __import__("os").environ.get("FLASK_DEBUG", "false").lower() == "true"

    with application.app_context():
        from app.database import db

        db.create_all()

    application.run(debug=debug_mode, host="127.0.0.1", port=get_port())
