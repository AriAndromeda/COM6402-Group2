"""US04c – happy-path cooling-space bookings (TDD)."""


def _create_request(client):
    response = client.post(
        "/api/requests",
        json={
            "description": "Needs a cool place this afternoon",
            "category": "cooling",
            "area": "Bolton",
        },
    )
    assert response.status_code == 201
    return response.json["id"]


def _create_centre(client, staff_headers, capacity=10):
    """Create a cooling centre using authorised staff credentials."""

    response = client.post(
        "/api/centres",
        json={
            "name": "Bolton Community Centre",
            "area": "Bolton",
            "capacity": capacity,
            "opening_hours": "09:00-17:00",
            "status": "open",
        },
        headers=staff_headers,
    )

    assert response.status_code == 201
    return response.json

def test_cooling_centre_to_dict():
    from app import CoolingCentre

    centre = CoolingCentre(
        id=1,
        name="Bolton Community Centre",
        area="Bolton",
        capacity=10,
        spaces_available=10,
        opening_hours="09:00-17:00",
        status="open",
    )
    assert centre.to_dict() == {
        "id": 1,
        "name": "Bolton Community Centre",
        "area": "Bolton",
        "capacity": 10,
        "spaces_available": 10,
        "opening_hours": "09:00-17:00",
        "status": "open",
    }


def test_booking_to_dict():
    from app import Booking

    booking = Booking(
        id=1,
        request_id=2,
        centre_id=3,
        booking_date="2026-11-24",
        booking_time="14:00",
        spaces_required=2,
        status="confirmed",
    )
    assert booking.to_dict() == {
        "id": 1,
        "request_id": 2,
        "centre_id": 3,
        "booking_date": "2026-11-24",
        "booking_time": "14:00",
        "spaces_required": 2,
        "status": "confirmed",
    }


def test_create_booking_happy_path(client, staff_headers):
    request_id = _create_request(client)
    centre = _create_centre(client, staff_headers, capacity=10)
    centre_id = centre["id"]
    assert centre["spaces_available"] == 10

    response = client.post(
        "/api/bookings",
        json={
            "request_id": request_id,
            "centre_id": centre_id,
            "booking_date": "2026-11-24",
            "booking_time": "14:00",
            "spaces_required": 2,
        },
        headers=staff_headers,
    )

    assert response.status_code == 201
    body = response.json
    assert body["request_id"] == request_id
    assert body["centre_id"] == centre_id
    assert body["booking_date"] == "2026-11-24"
    assert body["booking_time"] == "14:00"
    assert body["spaces_required"] == 2
    assert body["status"] == "confirmed"
    assert "id" in body

    # Remaining capacity reduced by spaces_required
    centre_after = client.get(f"/api/centres/{centre_id}")
    assert centre_after.status_code == 200
    assert centre_after.json["capacity"] == 10
    assert centre_after.json["spaces_available"] == 8

    # Booking can be retrieved
    booking = client.get(f"/api/bookings/{body['id']}")
    assert booking.status_code == 200
    assert booking.json["id"] == body["id"]
