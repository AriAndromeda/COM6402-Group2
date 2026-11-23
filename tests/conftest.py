import pytest

from app import app, db


@pytest.fixture
def client(tmp_path):
    """Isolated SQLite DB per test, using the real Flask app."""
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'test.db'}",
    )

    # Rebuild the default engine against the per-test URI.
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
