"""Staff authentication and authorisation decorators (US06)."""

import hashlib
import secrets
from functools import wraps

from flask import g, jsonify, request

from app.database import db
from app.models.staff_user import StaffUser


def require_staff(*allowed_roles):
    """Restrict an endpoint to authenticated, authorised staff."""

    def decorator(view_function):
        from app.utils.security import log_security_event

        @wraps(view_function)
        def wrapper(*args, **kwargs):

            # Read the Bearer token from the request header
            authorization = request.headers.get("Authorization", "")
            parts = authorization.split()

            if (
                len(parts) != 2
                or parts[0].lower() != "bearer"
                or not parts[1]
            ):
                # US19 AC4: Log failed authentication attempts.
                log_security_event(
                    "AUTH_FAILED",
                    "Missing or malformed Bearer token",
                )
                return jsonify({"error": "Authentication required"}), 401

            # Hash the supplied token before database lookup
            token_hash = hashlib.sha256(parts[1].encode("utf-8")).hexdigest()

            staff = db.session.scalar(
                db.select(StaffUser).where(StaffUser.token_hash == token_hash)
            )

            # Reject unknown or inactive staff accounts
            if staff is None or not staff.is_active:
                log_security_event(
                    "AUTH_FAILED",
                    f"Invalid or inactive credentials (token hash={token_hash[:8]}...)",
                )
                return jsonify({"error": "Invalid or inactive credentials"}), 401

            # Check whether the staff role is authorised
            if staff.role not in allowed_roles:
                log_security_event(
                    "ACCESS_DENIED",
                    f"Insufficient permissions for role={staff.role}",
                )
                return jsonify({"error": "Insufficient permissions"}), 403

            # Make the authenticated identity available to the route
            g.current_staff = staff

            return view_function(*args, **kwargs)

        return wrapper

    return decorator


def require_supervisor(view_function):
    """Restrict an endpoint to supervisor role only (US19 AC2/AC4)."""
    return require_staff("supervisor")(view_function)


def generate_staff_token():
    """Generate a cryptographically secure staff access token."""
    return secrets.token_urlsafe(32)


def provision_staff(username, role="staff"):
    """Provision a staff account without exposing a public registration API."""

    # Validate the username
    if not isinstance(username, str) or not username.strip():
        raise ValueError("A valid username is required")

    username = username.strip()

    if len(username) > 80:
        raise ValueError("Username must not exceed 80 characters")

    # Restrict accounts to approved roles
    if role not in ("staff", "supervisor"):
        raise ValueError("Invalid staff role")

    # Prevent duplicate staff accounts
    existing_staff = db.session.scalar(
        db.select(StaffUser).where(StaffUser.username == username)
    )

    if existing_staff is not None:
        raise ValueError("Staff username already exists")

    # Generate a cryptographically secure access token
    token = generate_staff_token()

    # Store only the token hash
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    staff = StaffUser(
        username=username,
        role=role,
        token_hash=token_hash,
        is_active=True,
    )

    db.session.add(staff)
    db.session.commit()

    # Return the token once to the trusted provisioning caller
    return token
