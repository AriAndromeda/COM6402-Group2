
"""US07c: Request status persistence, validation and audit tests."""

from app import AuditLog, StaffUser, SupportRequest, db


def create_test_request(client):
    """Create a fictional support request."""
    response = client.post(
        "/api/requests",
        json={
            "description": "US07c welfare test",
            "category": "welfare",
            "area": "Bolton",
            "priority": "medium",
        },
    )

    assert response.status_code == 201
    return response.json["id"]


def test_status_update_is_saved_and_audited(client, staff_headers):
    request_id = create_test_request(client)

    response = client.patch(
        f"/api/requests/{request_id}",
        json={"status": "in progress"},
        headers=staff_headers,
    )

    assert response.status_code == 200

    record = db.session.get(SupportRequest, request_id)
    assert record.status == "in progress"

    logs = db.session.query(AuditLog).filter_by(
        resource_type="support_request",
        resource_id=request_id,
        action="update",
    ).all()

    assert len(logs) == 1

    staff = db.session.get(StaffUser, logs[0].staff_user_id)
    assert staff.username == "regression_staff"
    assert logs[0].timestamp is not None


def test_invalid_status_does_not_modify_database(
    client, staff_headers
):
    request_id = create_test_request(client)

    response = client.patch(
        f"/api/requests/{request_id}",
        json={"status": "invalid"},
        headers=staff_headers,
    )

    assert response.status_code == 400

    record = db.session.get(SupportRequest, request_id)
    assert record.status == "new"

    assert db.session.query(AuditLog).filter_by(
        resource_type="support_request",
        resource_id=request_id,
    ).count() == 0


def test_unauthenticated_update_is_rejected(client):
    request_id = create_test_request(client)

    response = client.patch(
        f"/api/requests/{request_id}",
        json={"status": "completed"},
    )

    assert response.status_code == 401

    record = db.session.get(SupportRequest, request_id)
    assert record.status == "new"

    assert db.session.query(AuditLog).filter_by(
        resource_type="support_request",
        resource_id=request_id,
    ).count() == 0
