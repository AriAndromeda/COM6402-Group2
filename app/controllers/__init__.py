"""Re-export all blueprint controllers."""

from app.controllers.requests_bp import bp as requests_bp
from app.controllers.centres_bp import bp as centres_bp
from app.controllers.bookings_bp import bp as bookings_bp
from app.controllers.supervisor_bp import bp as supervisor_bp

__all__ = [
    "requests_bp",
    "centres_bp",
    "bookings_bp",
    "supervisor_bp",
]
