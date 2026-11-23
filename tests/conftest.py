
import pytest
from flask import Flask
from app import app, db


@pytest.fixture
def client():
    # Create a separate testing application
    test_app = Flask(__name__)

    test_app.config["TESTING"] = True
    test_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"

    db.init_app(test_app)

    # Copy the existing API routes
    for rule in app.url_map.iter_rules():
        if rule.endpoint != "static":
            test_app.add_url_rule(
                rule.rule,
                endpoint=rule.endpoint,
                view_func=app.view_functions[rule.endpoint],
                methods=rule.methods
            )

    # Create the testing database
    with test_app.app_context():
        db.create_all()

    yield test_app.test_client()

    # Remove testing data afterwards
    with test_app.app_context():
        db.session.remove()
        db.drop_all()
