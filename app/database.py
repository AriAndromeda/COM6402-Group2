"""Shared SQLAlchemy instance for the Heat Shield application."""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def create_db(app):
    """Attach the shared db to a Flask app and return it."""
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///heatshield.db"
    db.init_app(app)
    return db
