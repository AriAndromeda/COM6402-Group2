
def test_create_and_retrieve_request(client):
    # Create a fictional support request
    data = {
        "description": "Water assistance needed",
        "category": "welfare",
        "area": "Bolton"
    }

    # Send a POST request
    response = client.post("/api/requests", json=data)

    # Check the request was created
    assert response.status_code == 201

    # Get the created request ID
    request_id = response.json["id"]

    # Retrieve the request using GET
    result = client.get(f"/api/requests/{request_id}")

    # Check the saved information
    assert result.status_code == 200
    assert result.json["description"] == "Water assistance needed"
    assert result.json["area"] == "Bolton"


def test_update_request(client):
    # Create a support request
    data = {
        "description": "Water assistance needed",
        "category": "welfare",
        "area": "Bolton"
    }

    response = client.post("/api/requests", json=data)
    request_id = response.json["id"]

    # Update the request status
    updated = client.patch(
        f"/api/requests/{request_id}",
        json={"status": "in progress"}
    )

    # Check the update was successful
    assert updated.status_code == 200
    assert updated.json["status"] == "in progress"

    # Verify the updated status was saved
    result = client.get(f"/api/requests/{request_id}")

    assert result.status_code == 200
    assert result.json["status"] == "in progress"


def test_missing_required_field(client):
    # Create a request without a description
    data = {
        "category": "welfare",
        "area": "Bolton"
    }

    # Attempt to create the request
    response = client.post("/api/requests", json=data)

    # The API should reject invalid information
    assert response.status_code == 400
    assert response.json["error"] == "description is required"

    # Confirm the invalid request was not saved
    result = client.get("/api/requests")

    assert result.json == []


def test_request_not_found(client):
    # Try to retrieve a request that does not exist
    response = client.get("/api/requests/999")

    # Check that the API returns 404
    assert response.status_code == 404

    # Check the error message
    assert response.json["error"] == "Request not found"


def test_filter_requests_by_area(client):
    # Create requests in two different areas
    client.post("/api/requests", json={
        "description": "Water assistance",
        "category": "welfare",
        "area": "Bolton"
    })

    client.post("/api/requests", json={
        "description": "Cooling space needed",
        "category": "cooling",
        "area": "Horwich"
    })

    # Filter requests for Bolton only
    response = client.get("/api/requests?area=Bolton")

    # Verify the filtering works
    assert response.status_code == 200
    assert len(response.json) == 1
    assert response.json[0]["area"] == "Bolton"


def test_invalid_json_input(client):
    # Send invalid data instead of JSON
    response = client.post(
        "/api/requests",
        data="Invalid data",
        content_type="text/plain"
    )

    # Check that the API rejects it
    assert response.status_code == 400

    # Verify nothing was saved
    result = client.get("/api/requests")
    assert result.json == []

def test_delete_request(client):
    # Create a support request
    response = client.post("/api/requests", json={
        "description": "Water assistance needed",
        "category": "welfare",
        "area": "Bolton"
    })

    assert response.status_code == 201
    request_id = response.json["id"]

    # Delete the support request
    deleted = client.delete(f"/api/requests/{request_id}")

    # Successful deletion returns HTTP 204
    assert deleted.status_code == 204

    # Confirm the deleted request no longer exists
    result = client.get(f"/api/requests/{request_id}")
    assert result.status_code == 404