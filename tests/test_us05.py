
import pytest

def test_filter_by_category(client):
    # Create two support requests with different categories
    client.post("/api/requests", json={
        "description": "Water assistance needed",
        "category": "welfare",
        "area": "Bolton"
    })

    client.post("/api/requests", json={
        "description": "Cooling centre required",
        "category": "cooling",
        "area": "Manchester"
    })

    # Request only welfare support records
    response = client.get("/api/requests?category=welfare")

    # Verify the HTTP response
    assert response.status_code == 200

    # Verify only the matching request is returned
    assert len(response.json) == 1
    assert response.json[0]["category"] == "welfare"
    assert response.json[0]["description"] == "Water assistance needed"

def test_filter_by_status(client):
    # Create a new support request
    client.post("/api/requests", json={
        "description": "Water assistance needed",
        "category": "welfare",
        "area": "Bolton",
        "status": "new"
    })

    # Create a request already in progress
    client.post("/api/requests", json={
        "description": "Cooling assistance required",
        "category": "cooling",
        "area": "Manchester",
        "status": "in progress"
    })

    # Filter requests by status
    response = client.get("/api/requests?status=in%20progress")

    # Verify the response
    assert response.status_code == 200
    assert len(response.json) == 1
    assert response.json[0]["status"] == "in progress"
    assert response.json[0]["description"] == "Cooling assistance required"

def test_filter_by_priority(client):
    # Create requests with different priorities
    client.post("/api/requests", json={
        "description": "Urgent water assistance",
        "category": "welfare",
        "area": "Bolton",
        "priority": "high"
    })

    client.post("/api/requests", json={
        "description": "General cooling advice",
        "category": "cooling",
        "area": "Manchester",
        "priority": "low"
    })

    # Filter for high-priority requests
    response = client.get("/api/requests?priority=high")

    # Verify only the high-priority request is returned
    assert response.status_code == 200
    assert len(response.json) == 1
    assert response.json[0]["priority"] == "high"
    assert response.json[0]["description"] == "Urgent water assistance"

def test_filter_by_area(client):
    # Create requests in different areas
    client.post("/api/requests", json={
        "description": "Water assistance needed",
        "category": "welfare",
        "area": "Bolton"
    })

    client.post("/api/requests", json={
        "description": "Cooling assistance needed",
        "category": "cooling",
        "area": "Manchester"
    })

    # Search using lowercase to verify case-insensitive filtering
    response = client.get("/api/requests?area=bolton")

    # Verify only the Bolton request is returned
    assert response.status_code == 200
    assert len(response.json) == 1
    assert response.json[0]["area"] == "Bolton"
    assert response.json[0]["description"] == "Water assistance needed"

def test_combined_filters(client):
    # Create three support requests
    requests = [
        {
            "description": "Urgent water assistance",
            "category": "welfare",
            "area": "Bolton",
            "priority": "high",
            "status": "new"
        },
        {
            "description": "General welfare assistance",
            "category": "welfare",
            "area": "Bolton",
            "priority": "low",
            "status": "new"
        },
        {
            "description": "Urgent cooling assistance",
            "category": "cooling",
            "area": "Manchester",
            "priority": "high",
            "status": "new"
        }
    ]

    for data in requests:
        response = client.post("/api/requests", json=data)
        assert response.status_code == 201

    # Apply all four filters together
    response = client.get(
        "/api/requests",
        query_string={
            "category": "welfare",
            "area": "bolton",
            "priority": "high",
            "status": "new"
        }
    )

    # Verify only the matching request is returned
    assert response.status_code == 200
    assert len(response.json) == 1
    assert response.json[0]["description"] == "Urgent water assistance"

def test_health_check(client):
    # Request the API health status
    response = client.get("/api/health")

    # Verify that the API responds successfully
    assert response.status_code == 200

    # Verify the expected JSON response
    assert response.json == {"status": "ok"}

@pytest.mark.parametrize(
    "filters",
    [
        {"category": "medical"},
        {"status": "completed"},
        {"priority": "critical"},
        {"area": "Liverpool"},
        {
            "category": "welfare",
            "priority": "high",
            "area": "Manchester"
        }
    ]
)

def test_filters_with_no_matching_results(client, filters):
    # Create an existing support request
    response = client.post("/api/requests", json={
        "description": "Water assistance needed",
        "category": "welfare",
        "area": "Bolton",
        "priority": "low",
        "status": "new"
    })

    assert response.status_code == 201

    # Apply filters that should not match this request
    response = client.get(
        "/api/requests",
        query_string=filters
    )

    # The API should return an empty list
    assert response.status_code == 200
    assert response.json == []

@pytest.mark.parametrize(
    "filters, expected_descriptions",
    [
        (
            {"category": "welfare", "area": "Bolton"},
            ["Urgent water support", "General welfare support"]
        ),
        (
            {
                "category": "welfare",
                "area": "Bolton",
                "priority": "high"
            },
            ["Urgent water support"]
        ),
        (
            {
                "category": "welfare",
                "area": "bolton",
                "priority": "high",
                "status": "new"
            },
            ["Urgent water support"]
        )
    ]
)
def test_multiple_filter_combinations(
    client, filters, expected_descriptions
):
    # Create support requests with different attributes
    requests = [
        {
            "description": "Urgent water support",
            "category": "welfare",
            "area": "Bolton",
            "priority": "high",
            "status": "new"
        },
        {
            "description": "General welfare support",
            "category": "welfare",
            "area": "Bolton",
            "priority": "low",
            "status": "new"
        },
        {
            "description": "Urgent cooling support",
            "category": "cooling",
            "area": "Manchester",
            "priority": "high",
            "status": "in progress"
        }
    ]

    for data in requests:
        response = client.post("/api/requests", json=data)
        assert response.status_code == 201

    # Apply the selected combination of filters
    response = client.get(
        "/api/requests",
        query_string=filters
    )

    assert response.status_code == 200

    # Verify the exact matching records
    actual_descriptions = [
        item["description"] for item in response.json
    ]

    assert sorted(actual_descriptions) == sorted(
        expected_descriptions
    )

@pytest.mark.parametrize(
    "filters",
    [
        {"category": "invalid-category"},
        {"status": "unknown"},
        {"priority": "urgent"},
        {"area": "NonexistentArea"}
    ]
)

def test_invalid_filter_values(client, filters):
    # Create a valid support request
    response = client.post("/api/requests", json={
        "description": "Water assistance needed",
        "category": "welfare",
        "area": "Bolton",
        "priority": "high",
        "status": "new"
    })

    assert response.status_code == 201

    # Search using an invalid or unmatched filter value
    response = client.get(
        "/api/requests",
        query_string=filters
    )

    # Verify the current API filtering behaviour
    assert response.status_code == 200
    assert response.json == []