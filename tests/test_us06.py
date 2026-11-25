
import hashlib
from typing import Literal

import pytest
from flask.testing import FlaskClient

from app import (
    AuditLog,
    StaffUser,
    db,
    generate_staff_token,
    provision_staff,
)


def test_unauthenticated_user_cannot_update_request(client: FlaskClient):
    """Unauthenticated users must not modify support requests."""

    # Create a request as test setup
    response = client.post("/api/requests", json={
        "description": "Water assistance needed",
        "category": "welfare",
        "area": "Bolton",
        "priority": "medium"
    })

    assert response.status_code == 201
    request_id = response.json["id"]

    # Attempt to update the request without authentication
    response = client.patch(
        f"/api/requests/{request_id}",
        json={"priority": "high"}
    )

    # Unauthenticated changes must be rejected
    assert response.status_code == 401

    # Verify the original record remains unchanged
    record = client.get(f"/api/requests/{request_id}")

    assert record.status_code == 200
    assert record.json["priority"] == "medium"

def test_authorised_staff_can_update_request(client: FlaskClient):
    """Authenticated staff can update support requests."""

    # Create a support request for testing
    response = client.post("/api/requests", json={
        "description": "Water assistance needed",
        "category": "welfare",
        "area": "Bolton",
        "priority": "medium"
    })

    assert response.status_code == 201
    request_id = response.json["id"]

    # Create a test-only staff credential
    token = "us06-test-token-only"

    staff = StaffUser(
        username="test_staff",
        role="staff",
        token_hash=hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest(),
        is_active=True
    )

    db.session.add(staff)
    db.session.commit()

    # Update the request using authorised credentials
    response = client.patch(
        f"/api/requests/{request_id}",
        json={"priority": "high"},
        headers={
            "Authorization": f"Bearer {token}"
        }
    )

    assert response.status_code == 200
    assert response.json["priority"] == "high"

    # Verify the change was saved
    record = client.get(f"/api/requests/{request_id}")

    assert record.status_code == 200
    assert record.json["priority"] == "high"

def test_user_without_permission_cannot_update_request(client: FlaskClient):
    """Authenticated users without permission must be rejected."""

    # Create a support request
    response = client.post("/api/requests", json={
        "description": "Water assistance needed",
        "category": "welfare",
        "area": "Bolton",
        "priority": "medium"
    })

    assert response.status_code == 201
    request_id = response.json["id"]

    # Create an authenticated user without editing permission
    token = "us06-viewer-test-token"

    viewer = StaffUser(
        username="test_viewer",
        role="viewer",
        token_hash=hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest(),
        is_active=True
    )

    db.session.add(viewer)
    db.session.commit()

    # Attempt an update using viewer credentials
    response = client.patch(
        f"/api/requests/{request_id}",
        json={"priority": "high"},
        headers={
            "Authorization": f"Bearer {token}"
        }
    )

    # Authenticated, but not authorised
    assert response.status_code == 403

    # Verify the original data remains unchanged
    record = client.get(f"/api/requests/{request_id}")

    assert record.status_code == 200
    assert record.json["priority"] == "medium"

    import pytest


@pytest.mark.parametrize(
    "credential_type",
    ["invalid", "inactive"]
)
def test_invalid_or_inactive_credentials(client: FlaskClient, credential_type: Literal['invalid'] | Literal['inactive']):
    """Invalid and inactive staff credentials must be rejected."""

    # Create a support request
    response = client.post("/api/requests", json={
        "description": "Urgent welfare assistance",
        "category": "welfare",
        "area": "Bolton",
        "priority": "medium"
    })

    assert response.status_code == 201
    request_id = response.json["id"]

    if credential_type == "invalid":
        token = "unknown-test-token"

    else:
        token = "inactive-test-token"

        # Create a deactivated staff account
        staff = StaffUser(
            username="inactive_staff",
            role="staff",
            token_hash=hashlib.sha256(
                token.encode("utf-8")
            ).hexdigest(),
            is_active=False
        )

        db.session.add(staff)
        db.session.commit()

    # Attempt to modify a request
    response = client.patch(
        f"/api/requests/{request_id}",
        json={"priority": "high"},
        headers={
            "Authorization": f"Bearer {token}"
        }
    )

    # Both cases must be rejected
    assert response.status_code == 401

    # Confirm the rejected change was not saved
    record = client.get(f"/api/requests/{request_id}")

    assert record.status_code == 200
    assert record.json["priority"] == "medium"

def test_unauthenticated_user_cannot_create_booking(client, staff_headers):
    """Unauthenticated users must not create bookings."""

    # Create a support request for the test
    response = client.post(
    "/api/centres",
    json={
        "name": "Bolton Community Centre",
        "area": "Bolton",
        "capacity": 10,
        "status": "open"
    },
    headers=staff_headers
)
    assert response.status_code == 201
    request_id = response.json["id"]

    # Create a cooling centre with available spaces
    response = client.post("/api/centres", json={
        "name": "Bolton Community Centre",
        "area": "Bolton",
        "capacity": 10,
        "status": "open"
    },
    headers=staff_headers
)
    assert response.status_code == 201
    centre_id = response.json["id"]

    # Attempt to create a booking without authentication
    response = client.post("/api/bookings", json={
        "request_id": request_id,
        "centre_id": centre_id,
        "booking_date": "2026-11-25",
        "booking_time": "14:00",
        "spaces_required": 2
    })

    # Unauthenticated booking attempts must be rejected
    assert response.status_code == 401

    # Confirm capacity remains unchanged
    centre = client.get(f"/api/centres/{centre_id}")

    assert centre.status_code == 200
    assert centre.json["spaces_available"] == 10


def test_authorised_staff_can_create_booking(client, staff_headers):
    """Authorised staff can create a booking successfully."""

    # Create the required support request
    response = client.post(
    "/api/requests",
    json={
        "description": "Cooling assistance needed",
        "category": "cooling",
        "area": "Bolton"
    }
)

    assert response.status_code == 201
    request_id = response.json["id"]

    # Create a cooling centre with 10 available spaces
    response = client.post("/api/centres", json={
        "name": "Bolton Community Centre",
        "area": "Bolton",
        "capacity": 10,
        "status": "open"
    },
    headers=staff_headers
)

    assert response.status_code == 201
    centre_id = response.json["id"]

    # Create an authorised staff account for testing
    token = "us06-booking-test-token"

    staff = StaffUser(
        username="booking_staff",
        role="staff",
        token_hash=hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest(),
        is_active=True
    )

    db.session.add(staff)
    db.session.commit()

    # Create a booking using authenticated credentials
    response = client.post(
        "/api/bookings",
        json={
            "request_id": request_id,
            "centre_id": centre_id,
            "booking_date": "2026-11-25",
            "booking_time": "14:00",
            "spaces_required": 2
        },
        headers={
            "Authorization": f"Bearer {token}"
        }
    )

    # Verify successful booking creation
    assert response.status_code == 201
    assert response.json["status"] == "confirmed"
    assert response.json["spaces_required"] == 2

    # Verify that the booking was persisted
    booking_id = response.json["id"]
    saved_booking = client.get(f"/api/bookings/{booking_id}")

    assert saved_booking.status_code == 200
    assert saved_booking.json["id"] == booking_id

    # Verify the centre's remaining capacity
    centre = client.get(f"/api/centres/{centre_id}")

    assert centre.status_code == 200
    assert centre.json["spaces_available"] == 8


def test_successful_update_creates_audit_record(client, staff_headers):
    """A successful staff update must create an audit record."""

    # Create a support request
    response = client.post("/api/requests", json={
        "description": "Water assistance needed",
        "category": "welfare",
        "area": "Bolton",
        "priority": "medium"
    })

    assert response.status_code == 201
    request_id = response.json["id"]

    # Create an authorised test staff member
    token = "us06-audit-test-token"

    staff = StaffUser(
        username="audit_staff",
        role="staff",
        token_hash=hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest(),
        is_active=True
    )

    db.session.add(staff)
    db.session.commit()
    staff_id = staff.id

    # Update the request using staff credentials
    response = client.patch(
        f"/api/requests/{request_id}",
        json={"priority": "high"},
        headers={
            "Authorization": f"Bearer {token}"
        }
    )

    assert response.status_code == 200

    # Retrieve audit records from the database
    audit_records = db.session.scalars(
        db.select(AuditLog)
    ).all()

    # Exactly one audit entry should exist
    assert len(audit_records) == 1

    audit = audit_records[0]

    # Verify accountability information
    assert audit.staff_user_id == staff_id
    assert audit.action == "update"
    assert audit.resource_type == "support_request"
    assert audit.resource_id == request_id
    assert audit.timestamp is not None


def test_successful_booking_creates_audit_record(client, staff_headers):
    """A successful booking must create a staff audit record."""

    # Create the support request needed for the booking
    response = client.post("/api/requests", json={
        "description": "Cooling assistance required",
        "category": "cooling",
        "area": "Bolton"
    },
    headers=staff_headers
)

    assert response.status_code == 201
    request_id = response.json["id"]

    # Create a cooling centre
    response = client.post("/api/centres", json={
        "name": "Bolton Community Centre",
        "area": "Bolton",
        "capacity": 10,
        "status": "open"
    }, headers=staff_headers
)

    assert response.status_code == 201
    centre_id = response.json["id"]

    # Create an authorised staff member
    token = "us06-booking-audit-test-token"

    staff = StaffUser(
        username="booking_audit_staff",
        role="staff",
        token_hash=hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest(),
        is_active=True
    )

    db.session.add(staff)
    db.session.commit()
    staff_id = staff.id

    # Create a booking with staff credentials
    response = client.post(
        "/api/bookings",
        json={
            "request_id": request_id,
            "centre_id": centre_id,
            "booking_date": "2026-11-25",
            "booking_time": "14:00",
            "spaces_required": 2
        },
        headers={
            "Authorization": f"Bearer {token}"
        }
    )

    assert response.status_code == 201
    booking_id = response.json["id"]

    # Retrieve only successful booking audit records
    audit_records = db.session.scalars(
    db.select(AuditLog).where(
        AuditLog.resource_type == "booking",
        AuditLog.action == "create"
    )
).all()

    # Verify exactly one audit record was created
    assert len(audit_records) == 1

    audit = audit_records[0]

    # Verify staff accountability information
    assert audit.staff_user_id == staff_id
    assert audit.action == "create"
    assert audit.resource_type == "booking"
    assert audit.resource_id == booking_id
    assert audit.timestamp is not None

    # Verify the centre's remaining capacity
    centre = client.get(f"/api/centres/{centre_id}")

    assert centre.status_code == 200
    assert centre.json["spaces_available"] == 8


def test_rejected_booking_does_not_create_audit_record(client, staff_headers):
    """Rejected bookings must not create successful audit entries."""

    # Create a support request
    response = client.post("/api/requests", json={
        "description": "Cooling assistance needed",
        "category": "cooling",
        "area": "Bolton"
    },
    headers=staff_headers
    )

    assert response.status_code == 201
    request_id = response.json["id"]

    # Create a closed cooling centre
    response = client.post("/api/centres", json={
        "name": "Bolton Community Centre",
        "area": "Bolton",
        "capacity": 10,
        "status": "closed"
    },
    headers=staff_headers
)

    assert response.status_code == 201
    centre_id = response.json["id"]

    # Create an authorised staff account
    token = "us06-rejected-booking-test-token"

    staff = StaffUser(
        username="rejected_booking_staff",
        role="staff",
        token_hash=hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest(),
        is_active=True
    )

    db.session.add(staff)
    db.session.commit()

    # Attempt to book a closed centre
    response = client.post(
        "/api/bookings",
        json={
            "request_id": request_id,
            "centre_id": centre_id,
            "booking_date": "2026-11-25",
            "booking_time": "14:00",
            "spaces_required": 2
        },
        headers={
            "Authorization": f"Bearer {token}"
        }
    )

    # Booking must be rejected
    assert response.status_code == 409
    assert response.json["error"] == "Centre is closed"

    # A rejected booking must not create a successful booking audit
    audit_records = db.session.scalars(
    db.select(AuditLog).where(
        AuditLog.resource_type == "booking",
        AuditLog.action == "create"
    )
).all()

    assert len(audit_records) == 0

    # Available capacity must remain unchanged
    centre = client.get(f"/api/centres/{centre_id}")

    assert centre.status_code == 200
    assert centre.json["spaces_available"] == 10

def test_unauthenticated_user_cannot_delete_request(client):
    """Unauthenticated users must not delete support requests."""

    response = client.post("/api/requests", json={
        "description": "Welfare assistance needed",
        "category": "welfare",
        "area": "Bolton"
    })

    assert response.status_code == 201
    request_id = response.json["id"]

    response = client.delete(f"/api/requests/{request_id}")

    assert response.status_code == 401

    # Confirm that the request still exists.
    record = client.get(f"/api/requests/{request_id}")

    assert record.status_code == 200


def test_successful_deletion_creates_audit_record(client):
    """Authorised deletion must create an audit record."""

    # Create a support request
    response = client.post("/api/requests", json={
        "description": "Welfare assistance needed",
        "category": "welfare",
        "area": "Bolton"
    })

    assert response.status_code == 201
    request_id = response.json["id"]

    # Create authorised test staff credentials
    token = "us06-delete-audit-test-token"

    staff = StaffUser(
        username="delete_audit_staff",
        role="staff",
        token_hash=hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest(),
        is_active=True
    )

    db.session.add(staff)
    db.session.commit()
    staff_id = staff.id

    # Delete the request using authorised credentials
    response = client.delete(
        f"/api/requests/{request_id}",
        headers={
            "Authorization": f"Bearer {token}"
        }
    )

    assert response.status_code == 204

    # Confirm the request has been deleted
    record = client.get(f"/api/requests/{request_id}")
    assert record.status_code == 404

    # Confirm an audit record was created
    audit_records = db.session.scalars(
        db.select(AuditLog)
    ).all()

    assert len(audit_records) == 1

    audit = audit_records[0]

    assert audit.staff_user_id == staff_id
    assert audit.action == "delete"
    assert audit.resource_type == "support_request"
    assert audit.resource_id == request_id
    assert audit.timestamp is not None

def test_unauthenticated_user_cannot_create_centre(client):
    """Unauthenticated users cannot register cooling centres."""

    response = client.post(
        "/api/centres",
        json={
            "name": "Bolton Community Centre",
            "area": "Bolton",
            "capacity": 10,
            "status": "open"
        }
    )

    assert response.status_code == 401

    centres = client.get("/api/centres")

    assert centres.status_code == 200
    assert centres.json == []


def test_successful_centre_creation_creates_audit_record(
    client, staff_headers
):
    """Authorised centre creation must produce an audit record."""

    # Register a cooling centre using staff credentials
    response = client.post(
        "/api/centres",
        json={
            "name": "Bolton Emergency Cooling Centre",
            "area": "Bolton",
            "capacity": 20,
            "status": "open"
        },
        headers=staff_headers
    )

    assert response.status_code == 201
    centre_id = response.json["id"]

    # Find the staff member who performed the operation
    token_hash = hashlib.sha256(
        "us06-regression-test-token".encode("utf-8")
    ).hexdigest()

    staff = db.session.scalar(
        db.select(StaffUser).where(
            StaffUser.token_hash == token_hash
        )
    )

    assert staff is not None

    # Retrieve audit records relating to centre creation
    audit_records = db.session.scalars(
        db.select(AuditLog).where(
            AuditLog.resource_type == "cooling_centre",
            AuditLog.action == "create"
        )
    ).all()

    assert len(audit_records) == 1

    audit = audit_records[0]

    assert audit.staff_user_id == staff.id
    assert audit.resource_id == centre_id
    assert audit.timestamp is not None


def test_audit_failure_rolls_back_request_update(
    client, staff_headers
):
    """Audit failure must prevent the request update being saved."""

    from sqlalchemy import text

    # Create a support request
    response = client.post(
        "/api/requests",
        json={
            "description": "Water assistance needed",
            "category": "welfare",
            "area": "Bolton",
            "priority": "medium"
        }
    )
    assert response.status_code == 201
    request_id = response.json["id"]

    # Simulate a database failure when inserting an audit record
    db.session.execute(text("""
        CREATE TRIGGER reject_audit_insert
        BEFORE INSERT ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'Simulated audit failure');
        END;
    """))
    db.session.commit()

    # Attempt an authorised request update
    with pytest.raises(Exception):
        client.patch(
            f"/api/requests/{request_id}",
            json={"priority": "high"},
            headers=staff_headers
        )

    # Clear the failed SQLAlchemy transaction
    db.session.rollback()

    # Confirm the original request was not modified
    record = client.get(f"/api/requests/{request_id}")

    assert record.status_code == 200
    assert record.json["priority"] == "medium"

    # Confirm no audit entry was persisted
    audit_records = db.session.scalars(
        db.select(AuditLog)
    ).all()

    assert len(audit_records) == 0

    # Remove the simulated failure trigger
    db.session.execute(text(
        "DROP TRIGGER reject_audit_insert"
    ))
    db.session.commit()


def test_staff_token_generation():
    """Generated staff tokens must be unique and unpredictable."""

    tokens = [generate_staff_token() for _ in range(100)]

    # Tokens must be non-empty strings.
    assert all(isinstance(token, str) for token in tokens)
    assert all(len(token) >= 32 for token in tokens)

    # No duplicate tokens should be generated.
    assert len(set(tokens)) == 100


def test_secure_staff_account_provisioning(client):
    """Staff provisioning must store a token hash, not the raw token."""

    # Provision a staff account
    token = provision_staff("new_staff_member", "staff")

    # A secure token must be returned
    assert isinstance(token, str)
    assert len(token) >= 32

    # Retrieve the newly created staff account
    staff = db.session.scalar(
        db.select(StaffUser).where(
            StaffUser.username == "new_staff_member"
        )
    )

    assert staff is not None
    assert staff.role == "staff"
    assert staff.is_active is True

    # Verify the raw token is never stored in the database
    expected_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    assert staff.token_hash == expected_hash
    assert staff.token_hash != token



def test_provision_staff_rejects_invalid_role(client):
    """Staff accounts must use an approved role."""

    with pytest.raises(ValueError, match="Invalid staff role"):
        provision_staff("invalid_role_user", "administrator")

    # Invalid accounts must not be persisted
    staff = db.session.scalar(
        db.select(StaffUser).where(
            StaffUser.username == "invalid_role_user"
        )
    )

    assert staff is None


def test_provision_staff_rejects_duplicate_username(client):
    """Staff usernames must be unique."""

    provision_staff("existing_staff", "staff")

    with pytest.raises(
        ValueError,
        match="Staff username already exists"
    ):
        provision_staff("existing_staff", "supervisor")

    # There must be only one account with this username
    accounts = db.session.scalars(
        db.select(StaffUser).where(
            StaffUser.username == "existing_staff"
        )
    ).all()

    assert len(accounts) == 1
    assert accounts[0].role == "staff"



def test_provisioned_staff_token_authorises_request_update(client):
    """A provisioned staff token must permit authorised updates."""

    # Create a support request
    response = client.post(
        "/api/requests",
        json={
            "description": "Water assistance required",
            "category": "welfare",
            "area": "Bolton",
            "priority": "medium"
        }
    )

    assert response.status_code == 201
    request_id = response.json["id"]

    # Provision a staff account and obtain its token
    token = provision_staff("new_authorised_staff", "staff")

    # Use the newly generated token
    response = client.patch(
        f"/api/requests/{request_id}",
        json={"priority": "high"},
        headers={
            "Authorization": f"Bearer {token}"
        }
    )

    assert response.status_code == 200
    assert response.json["priority"] == "high"

    # Verify that the update was persisted
    record = client.get(f"/api/requests/{request_id}")

    assert record.status_code == 200
    assert record.json["priority"] == "high"



def test_deactivated_staff_token_cannot_update_request(client):
    """Deactivated staff credentials must no longer authorise changes."""

    # Create a support request
    response = client.post(
        "/api/requests",
        json={
            "description": "Water assistance required",
            "category": "welfare",
            "area": "Bolton",
            "priority": "medium"
        }
    )

    assert response.status_code == 201
    request_id = response.json["id"]

    # Provision an authorised staff member
    token = provision_staff("revoked_staff", "staff")

    # Deactivate the staff account
    staff = db.session.scalar(
        db.select(StaffUser).where(
            StaffUser.username == "revoked_staff"
        )
    )

    assert staff is not None

    staff.is_active = False
    db.session.commit()

    # Attempt to use the previously issued token
    response = client.patch(
        f"/api/requests/{request_id}",
        json={"priority": "high"},
        headers={
            "Authorization": f"Bearer {token}"
        }
    )

    assert response.status_code == 401

    # Confirm the request remains unchanged
    record = client.get(f"/api/requests/{request_id}")

    assert record.status_code == 200
    assert record.json["priority"] == "medium"

    # Confirm no successful update audit record exists
    audits = db.session.scalars(
        db.select(AuditLog).where(
            AuditLog.resource_type == "support_request",
            AuditLog.action == "update",
            AuditLog.resource_id == request_id
        )
    ).all()

    assert len(audits) == 0

def test_supervisor_can_update_request(client):
    """A supervisor must be authorised to update support requests."""

    response = client.post(
        "/api/requests",
        json={
            "description": "Medical assistance required",
            "category": "medical",
            "area": "Bolton",
            "priority": "medium"
        }
    )

    assert response.status_code == 201
    request_id = response.json["id"]

    # Provision an account with the supervisor role
    token = provision_staff("test_supervisor", "supervisor")

    response = client.patch(
        f"/api/requests/{request_id}",
        json={"priority": "critical"},
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json["priority"] == "critical"

    # Verify the supervisor's action was audited
    supervisor = db.session.scalar(
        db.select(StaffUser).where(
            StaffUser.username == "test_supervisor"
        )
    )

    audit = db.session.scalar(
        db.select(AuditLog).where(
            AuditLog.staff_user_id == supervisor.id,
            AuditLog.action == "update",
            AuditLog.resource_type == "support_request",
            AuditLog.resource_id == request_id
        )
    )

    assert audit is not None
    assert audit.timestamp is not None
