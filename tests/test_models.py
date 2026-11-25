
from app import SupportRequest


def test_support_request_to_dict():
    # Arrange: Create a fictional support request
    record = SupportRequest(
        id=1,
        description="Water assistance needed",
        category="welfare",
        area="Bolton",
        priority="high",
        status="new"
    )

    # Expected dictionary representation (includes timestamp fields)
    expected_keys = {
        "id", "description", "category", "area", "priority", "status",
        "created_at", "updated_at"
    }

    # Act: Convert the model into a dictionary
    actual = record.to_dict()

    # Assert: Verify all expected keys are present with correct values
    assert set(actual.keys()) == expected_keys
    assert actual["id"] == 1
    assert actual["description"] == "Water assistance needed"
    assert actual["category"] == "welfare"
    assert actual["area"] == "Bolton"
    assert actual["priority"] == "high"
    assert actual["status"] == "new"
    # Timestamps should be present and non-empty strings
    assert isinstance(actual["created_at"], str)
    assert len(actual["created_at"]) > 0
    assert isinstance(actual["updated_at"], str)
    assert len(actual["updated_at"]) > 0
