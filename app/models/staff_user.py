"""Staff user model (US06)."""

from app.database import db


class StaffUser(db.Model):
    """Store staff identities and their access roles."""

    __tablename__ = "staff_user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    role = db.Column(db.String(20), nullable=False, default="staff")
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
