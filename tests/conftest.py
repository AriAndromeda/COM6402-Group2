import hashlib
import pytest

from app import StaffUser, db
from app import app, db


@pytest.fixture
def client():
    """Shared in-memory SQLite DB; reset tables for each test."""
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite://",
    )

    # Point the app engine at the in-memory URI (once per test is fine; no files).
    engines = db._app_engines.setdefault(app, {})
    for engine in list(engines.values()):
        engine.dispose()
    engines.clear()
    engines[None] = db._make_engine(
        None,
        {"url": app.config["SQLALCHEMY_DATABASE_URI"]},
        app,
    )

    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


@pytest.fixture
def staff_headers(client):
    """Provide credentials for an authorised test staff member."""

    token = "us06-regression-test-token"

    staff = StaffUser(
        username="regression_staff",
        role="staff",
        token_hash=hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest(),
        is_active=True
    )

    db.session.add(staff)
    db.session.commit()

    return {
        "Authorization": f"Bearer {token}"
    }
