
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

    # Expected dictionary representation
    expected = {
        "id": 1,
        "description": "Water assistance needed",
        "category": "welfare",
        "area": "Bolton",
        "priority": "high",
        "status": "new"
    }

    # Act: Convert the model into a dictionary
    actual = record.to_dict()

    # Assert: Verify the output is correct
    assert actual == expected
