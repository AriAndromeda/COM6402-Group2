
"""US05 – Search, Filtering and API Testing.

Tests cover individual filters, combined queries, unmatched searches,
invalid filter values and the API health-check endpoint.

Framework: pytest
Run: python -m pytest tests/test_us05.py -v
"""

import pytest


def test_filter_by_category(client):
    """Verify that requests can be filtered by category."""
    response = client.post("/api/requests", json={
        "description": "Water assistance needed",
        "category": "welfare",
        "area": "Bolton"
    })
    assert response.status_code == 201

    response = client.post("/api/requests", json={
        "description": "Cooling centre required",
        "category": "cooling",
        "area": "Manchester"
    })
    assert response.status_code == 201

    # Retrieve only welfare requests
    response = client.get("/api/requests?category=welfare")

    assert response.status_code == 200
    assert len(response.json) == 1
    assert response.json[0]["category"] == "welfare"
    assert response.json[0]["description"] == "Water assistance needed"


def test_filter_by_status(client):
    """Verify that requests can be filtered by status."""
    response = client.post("/api/requests", json={
        "description": "Water assistance needed",
        "category": "welfare",
        "area": "Bolton",
        "status": "new"
    })
    assert response.status_code == 201

    response = client.post("/api/requests", json={
        "description": "Cooling assistance required",
        "category": "cooling",
        "area": "Manchester",
        "status": "in progress"
    })
    assert response.status_code == 201

    # Retrieve only requests that are in progress
    response = client.get("/api/requests?status=in%20progress")

    assert response.status_code == 200
    assert len(response.json) == 1
    assert response.json[0]["status"] == "in progress"
    assert response.json[0]["description"] == "Cooling assistance required"


def test_filter_by_priority(client):
    """Verify that requests can be filtered by priority."""
    response = client.post("/api/requests", json={
        "description": "Urgent water assistance",
        "category": "welfare",
        "area": "Bolton",
        "priority": "high"
    })
    assert response.status_code == 201

    response = client.post("/api/requests", json={
        "description": "General cooling advice",
        "category": "cooling",
        "area": "Manchester",
        "priority": "low"
    })
    assert response.status_code == 201

    # Retrieve only high-priority requests
    response = client.get("/api/requests?priority=high")

    assert response.status_code == 200
    assert len(response.json) == 1
    assert response.json[0]["priority"] == "high"
    assert response.json[0]["description"] == "Urgent water assistance"


def test_filter_by_area(client):
    """Verify case-insensitive filtering by geographical area."""
    response = client.post("/api/requests", json={
        "description": "Water assistance needed",
        "category": "welfare",
        "area": "Bolton"
    })
    assert response.status_code == 201

    response = client.post("/api/requests", json={
        "description": "Cooling assistance needed",
        "category": "cooling",
        "area": "Manchester"
    })
    assert response.status_code == 201

    # Lowercase search should match the stored value "Bolton"
    response = client.get("/api/requests?area=bolton")

    assert response.status_code == 200
    assert len(response.json) == 1
    assert response.json[0]["area"] == "Bolton"
    assert response.json[0]["description"] == "Water assistance needed"


def test_combined_filters(client):
    """Verify that all four filters work together."""
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

    # Apply category, area, priority and status filters
    response = client.get(
        "/api/requests",
        query_string={
            "category": "welfare",
            "area": "bolton",
            "priority": "high",
            "status": "new"
        }
    )

    assert response.status_code == 200
    assert len(response.json) == 1
    assert response.json[0]["description"] == "Urgent water assistance"


def test_health_check(client):
    """Verify that the API health-check endpoint responds correctly."""
    response = client.get("/api/health")

    assert response.status_code == 200
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
    """Verify that searches without matches return an empty list."""
    response = client.post("/api/requests", json={
        "description": "Water assistance needed",
        "category": "welfare",
        "area": "Bolton",
        "priority": "low",
        "status": "new"
    })
    assert response.status_code == 201

    response = client.get(
        "/api/requests",
        query_string=filters
    )

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
    """Verify two-, three- and four-parameter filter combinations."""
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

    response = client.get(
        "/api/requests",
        query_string=filters
    )

    assert response.status_code == 200

    # Compare the complete set of matching descriptions
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
    """Verify existing behaviour for unsupported filter values."""
    response = client.post("/api/requests", json={
        "description": "Water assistance needed",
        "category": "welfare",
        "area": "Bolton",
        "priority": "high",
        "status": "new"
    })
    assert response.status_code == 201

    response = client.get(
        "/api/requests",
        query_string=filters
    )

    # The current API returns an empty list, not HTTP 400
    assert response.status_code == 200
    assert response.json == []
