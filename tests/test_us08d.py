"""US08d: Concurrent booking and capacity-integrity tests."""

import hashlib

import pytest

from app import AuditLog, StaffUser, app, db

@pytest.fixture
def file_db(tmp_path):
    """Create an isolated file-based SQLite database for each test."""
    database_path = tmp_path / "us08d_test.db"

    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{database_path.as_posix()}",
    )

    engines = db._app_engines.setdefault(app, {})

    for engine in list(engines.values()):
        engine.dispose()

    engines.clear()
    engines[None] = db._make_engine(
        None,
        {
            "url": app.config["SQLALCHEMY_DATABASE_URI"],
            "connect_args": {"timeout": 10},
        },
        app,
    )

    with app.app_context():
        db.create_all()

        # Create an authorised staff account for testing.
        token = "us08d-test-token-only"

        staff = StaffUser(
            username="us08d_staff",
            role="staff",
            token_hash=hashlib.sha256(
                token.encode("utf-8")
            ).hexdigest(),
            is_active=True,
        )

        db.session.add(staff)
        db.session.commit()

        # Use authenticated requests in US08d tests.
        client = app.test_client()
        client.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {token}"

        yield client

        db.session.remove()
        db.drop_all()


def test_last_available_space_cannot_be_overbooked(file_db):
    """US08d: Once a centre is full, further bookings must be rejected."""

    client = file_db

    # Create a support request.
    request_response = client.post(
        "/api/requests",
        json={
            "description": "Resident requires cooling assistance",
            "category": "cooling",
            "area": "Bolton",
        },
    )
    assert request_response.status_code == 201
    request_id = request_response.json["id"]

    # Create a cooling centre with only one space.
    centre_response = client.post(
        "/api/centres",
        json={
            "name": "US08d Test Centre",
            "area": "Bolton",
            "capacity": 1,
            "status": "open",
        },
    )
    assert centre_response.status_code == 201
    centre_id = centre_response.json["id"]

    booking_data = {
        "request_id": request_id,
        "centre_id": centre_id,
        "booking_date": "2026-11-26",
        "booking_time": "14:00",
        "spaces_required": 1,
    }

    # First booking should succeed.
    first = client.post("/api/bookings", json=booking_data)
    assert first.status_code == 201

    # Second booking must be rejected.
    second = client.post("/api/bookings", json=booking_data)
    assert second.status_code == 409

    # Capacity must never become negative.
    centre = client.get(f"/api/centres/{centre_id}")
    assert centre.json["spaces_available"] == 0

    # Only one booking should exist.
    with app.app_context():
        from app import Booking

        assert db.session.query(Booking).count() == 1

        # One successful booking must produce exactly one audit record.
        booking_audits = db.session.query(AuditLog).filter_by(
            action="create",
            resource_type="booking",
        ).all()

        assert len(booking_audits) == 1
        assert booking_audits[0].staff_user_id is not None


def test_concurrent_bookings_do_not_overbook(file_db):
    """US08d: Competing bookings must not exceed available capacity."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import event

    from app import Booking, CoolingCentre

    client = file_db

    # Create two separate support requests.
    request_ids = []

    for number in range(2):
        response = client.post(
            "/api/requests",
            json={
                "description": f"Concurrent booking request {number}",
                "category": "cooling",
                "area": "Bolton",
            },
        )
        assert response.status_code == 201
        request_ids.append(response.json["id"])

    centre_response = client.post(
        "/api/centres",
        json={
            "name": "Concurrent Test Centre",
            "area": "Bolton",
            "capacity": 5,
            "status": "open",
        },
    )
    assert centre_response.status_code == 201
    centre_id = centre_response.json["id"]

    # Synchronise both requests after loading centre data.
    barrier = Barrier(2, timeout=10)

    def synchronise_centre_load(target, context):
        if target.id == centre_id:
            barrier.wait()

    event.listen(
        CoolingCentre,
        "load",
        synchronise_centre_load,
    )

    def make_booking(request_id):
        with app.test_client() as thread_client:
            return thread_client.post(
                "/api/bookings",
                headers={
                    "Authorization": "Bearer us08d-test-token-only",
                },
                json={
                    "request_id": request_id,
                    "centre_id": centre_id,
                    "booking_date": "2026-11-26",
                    "booking_time": "14:00",
                    "spaces_required": 4,
                },
            ).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(make_booking, request_ids))
    finally:
        event.remove(
            CoolingCentre,
            "load",
            synchronise_centre_load,
        )

    # Exactly one booking should succeed.
    assert sorted(results) == [201, 409]

    with app.app_context():
        assert db.session.query(Booking).count() == 1

    centre_after = client.get(f"/api/centres/{centre_id}")
    assert centre_after.json["spaces_available"] == 1


def test_booking_failure_rolls_back_capacity(file_db):
    """US08d: A failed booking must not reduce available capacity."""
    from sqlalchemy import event

    from app import Booking

    client = file_db

    request_response = client.post(
        "/api/requests",
        json={
            "description": "Resident requires emergency cooling",
            "category": "cooling",
            "area": "Bolton",
        },
    )
    assert request_response.status_code == 201
    request_id = request_response.json["id"]

    centre_response = client.post(
        "/api/centres",
        json={
            "name": "Rollback Test Centre",
            "area": "Bolton",
            "capacity": 10,
            "status": "open",
        },
    )
    assert centre_response.status_code == 201
    centre_id = centre_response.json["id"]

    # Simulate a database failure when the booking is inserted.
    def simulate_insert_failure(mapper, connection, target):
        raise RuntimeError("Simulated booking database failure")

    event.listen(Booking, "before_insert", simulate_insert_failure)

    try:
        with pytest.raises(
            RuntimeError,
            match="Simulated booking database failure",
        ):
            client.post(
                "/api/bookings",
                json={
                    "request_id": request_id,
                    "centre_id": centre_id,
                    "booking_date": "2026-11-26",
                    "booking_time": "14:00",
                    "spaces_required": 4,
                },
            )
    finally:
        event.remove(Booking, "before_insert", simulate_insert_failure)

    # Capacity must remain unchanged after rollback.
    centre_after = client.get(f"/api/centres/{centre_id}")

    assert centre_after.status_code == 200
    assert centre_after.json["spaces_available"] == 10

    # The failed booking must not be stored.
    with app.app_context():
        assert db.session.query(Booking).count() == 0


