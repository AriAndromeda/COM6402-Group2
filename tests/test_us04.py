"""Tests for US04a (Create requests) and US04b (Update requests).

Covers all acceptance criteria checklists:
  - Required field validation
  - Enumerated value validation (priority, status, category)
  - Unique ID returned on create
  - Default values when optional fields omitted
  - Welfare / practical-assistance records with minimal fields
  - PATCH update persistence and retrieval round-trip
  - Unknown field rejection
  - Edge cases: empty strings, whitespace-only, non-string types
"""

import pytest
from app import app, db


@pytest.fixture
def client():
    """Provide a test client with an in-memory SQLite database.

    Saves and restores the original config so tests don't mutate globals
    (Issue #3).  Each test gets a fresh empty database.
    """
    _original_uri = app.config["SQLALCHEMY_DATABASE_URI"]
    _original_testing = app.config.get("TESTING")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    app.config["TESTING"] = True

    with app.app_context():
        db.drop_all()
        db.create_all()

    yield app.test_client()

    with app.app_context():
        db.session.remove()
        db.drop_all()

    # Restore original config values.
    app.config["SQLALCHEMY_DATABASE_URI"] = _original_uri
    if _original_testing is not None:
        app.config["TESTING"] = _original_testing


# ======================================================================
# US04a — Create requests (Acceptance Criteria 1–5)
# ======================================================================

class TestUS04aCreateRequests:
    """US04a: Implement create endpoint that validates required fields."""

    # --- AC item 1: Define the required fields for creating a support request

    def test_create_missing_description_returns_400(self, client):
        resp = client.post("/api/requests", json={"category": "welfare", "area": "Bolton"})
        assert resp.status_code == 400
        assert "description" in resp.json["error"].lower()

    def test_create_missing_category_returns_400(self, client):
        resp = client.post("/api/requests", json={"description": "Help needed", "area": "Bolton"})
        assert resp.status_code == 400
        assert "category" in resp.json["error"].lower()

    def test_create_missing_area_returns_400(self, client):
        resp = client.post("/api/requests", json={"description": "Help needed", "category": "welfare"})
        assert resp.status_code == 400
        assert "area" in resp.json["error"].lower()

    def test_create_empty_string_description_returns_400(self, client):
        resp = client.post("/api/requests", json={
            "description": "", "category": "welfare", "area": "Bolton"
        })
        assert resp.status_code == 400

    def test_create_whitespace_only_description_returns_400(self, client):
        resp = client.post("/api/requests", json={
            "description": "   ", "category": "welfare", "area": "Bolton"
        })
        assert resp.status_code == 400

    # --- Non-string types for required fields (Issue #5)

    def test_create_int_description_returns_400(self, client):
        """Non-string type for a required field must be rejected."""
        resp = client.post("/api/requests", json={
            "description": 123, "category": "welfare", "area": "Bolton"
        })
        assert resp.status_code == 400
        assert "description" in resp.json["error"].lower()

    def test_create_none_category_returns_400(self, client):
        resp = client.post("/api/requests", json={
            "description": "Help needed", "category": None, "area": "Bolton"
        })
        assert resp.status_code == 400
        assert "category" in resp.json["error"].lower()

    def test_create_list_area_returns_400(self, client):
        resp = client.post("/api/requests", json={
            "description": "Help needed", "category": "welfare", "area": ["Bolton"]
        })
        assert resp.status_code == 400
        assert "area" in resp.json["error"].lower()

    def test_create_description_too_long_returns_400(self, client):
        """description must not exceed MAX_DESCRIPTION_LENGTH (500)."""
        long_desc = "x" * 501
        resp = client.post("/api/requests", json={
            "description": long_desc, "category": "welfare", "area": "Bolton"
        })
        assert resp.status_code == 400
        assert "description must be" in resp.json["error"].lower()

    def test_create_area_too_long_returns_400(self, client):
        """area must not exceed MAX_AREA_LENGTH (80)."""
        long_area = "x" * 81
        resp = client.post("/api/requests", json={
            "description": "Help needed", "category": "welfare", "area": long_area
        })
        assert resp.status_code == 400
        assert "area must be" in resp.json["error"].lower()

    def test_patch_description_too_long_returns_400(self, client):
        """PATCH description length is also enforced."""
        create_resp = client.post("/api/requests", json={
            "description": "Test", "category": "welfare", "area": "Bolton"
        })
        req_id = create_resp.json["id"]
        long_desc = "x" * 501
        resp = client.patch(f"/api/requests/{req_id}", json={"description": long_desc})
        assert resp.status_code == 400

    def test_patch_area_too_long_returns_400(self, client):
        """PATCH area length is also enforced."""
        create_resp = client.post("/api/requests", json={
            "description": "Test", "category": "welfare", "area": "Bolton"
        })
        req_id = create_resp.json["id"]
        long_area = "x" * 81
        resp = client.patch(f"/api/requests/{req_id}", json={"area": long_area})
        assert resp.status_code == 400

    def test_patch_non_string_description_returns_400(self, client):
        """PATCH with non-string required field must be rejected."""
        create_resp = client.post("/api/requests", json={
            "description": "Test", "category": "welfare", "area": "Bolton"
        })
        req_id = create_resp.json["id"]
        resp = client.patch(f"/api/requests/{req_id}", json={"description": 42})
        assert resp.status_code == 400

    def test_patch_non_string_area_returns_400(self, client):
        """PATCH with non-string area must be rejected."""
        create_resp = client.post("/api/requests", json={
            "description": "Test", "category": "welfare", "area": "Bolton"
        })
        req_id = create_resp.json["id"]
        resp = client.patch(f"/api/requests/{req_id}", json={"area": None})
        assert resp.status_code == 400

    def test_patch_two_phase_validation(self, client):
        """PATCH must not partially mutate when a later field is invalid (Issue #1)."""
        create_resp = client.post("/api/requests", json={
            "description": "Original", "category": "welfare", "area": "Bolton"
        })
        req_id = create_resp.json["id"]

        # description is valid, but priority is invalid — nothing should change.
        resp = client.patch(f"/api/requests/{req_id}", json={
            "description": "Updated",
            "priority": "urgent"  # invalid enum value
        })
        assert resp.status_code == 400

        # Verify the record was NOT mutated.
        get_resp = client.get(f"/api/requests/{req_id}")
        assert get_resp.json["description"] == "Original"

    # --- AC item 2: Implement create endpoint that validates required fields

    def test_create_invalid_priority_returns_400(self, client):
        resp = client.post("/api/requests", json={
            "description": "Help needed", "category": "welfare",
            "area": "Bolton", "priority": "urgent"
        })
        assert resp.status_code == 400
        assert "one of" in resp.json["error"].lower()

    def test_create_invalid_status_returns_400(self, client):
        resp = client.post("/api/requests", json={
            "description": "Help needed", "category": "welfare",
            "area": "Bolton", "status": "pending"
        })
        assert resp.status_code == 400

    def test_create_invalid_category_returns_400(self, client):
        resp = client.post("/api/requests", json={
            "description": "Help needed", "category": "emergency",
            "area": "Bolton"
        })
        assert resp.status_code == 400

    def test_create_valid_all_fields_returns_201(self, client):
        data = {
            "description": "Water assistance needed",
            "category": "welfare",
            "area": "Bolton",
            "priority": "high",
            "status": "new"
        }
        resp = client.post("/api/requests", json=data)
        assert resp.status_code == 201

    def test_create_non_json_body_returns_400(self, client):
        resp = client.post(
            "/api/requests",
            data="not json",
            content_type="application/json"
        )
        assert resp.status_code == 400

    # --- AC item 3: Return a unique ID when a request is saved successfully

    def test_create_returns_unique_id(self, client):
        data = {
            "description": "First request",
            "category": "welfare",
            "area": "Bolton"
        }
        resp1 = client.post("/api/requests", json=data)
        id1 = resp1.json["id"]

        data2 = {"description": "Second request", "category": "cooling", "area": "Manchester"}
        resp2 = client.post("/api/requests", json=data2)
        id2 = resp2.json["id"]

        assert isinstance(id1, int) and id1 > 0
        assert isinstance(id2, int) and id2 > 0
        assert id1 != id2

    def test_created_request_retrievable_by_id(self, client):
        data = {
            "description": "Retrievable request",
            "category": "medical",
            "area": "Liverpool"
        }
        create_resp = client.post("/api/requests", json=data)
        req_id = create_resp.json["id"]

        get_resp = client.get(f"/api/requests/{req_id}")
        assert get_resp.status_code == 200
        assert get_resp.json["description"] == "Retrievable request"

    # --- AC item 4: Support welfare/practical-assistance records with status only

    def test_welfare_record_defaults(self, client):
        """Minimal fields: description + category + area. Priority/status default."""
        data = {
            "description": "Water assistance needed",
            "category": "welfare",
            "area": "Bolton"
        }
        resp = client.post("/api/requests", json=data)
        assert resp.status_code == 201
        assert resp.json["priority"] == "medium"
        assert resp.json["status"] == "new"

    def test_practical_assistance_record_defaults(self, client):
        data = {
            "description": "Need help with groceries",
            "category": "practical-assistance",
            "area": "Manchester"
        }
        resp = client.post("/api/requests", json=data)
        assert resp.status_code == 201
        assert resp.json["priority"] == "medium"
        assert resp.json["status"] == "new"

    def test_welfare_record_with_explicit_status(self, client):
        data = {
            "description": "Elderly check needed",
            "category": "welfare",
            "area": "Bolton",
            "status": "in-progress"
        }
        resp = client.post("/api/requests", json=data)
        assert resp.status_code == 201
        assert resp.json["status"] == "in-progress"

    # --- AC item 5: Test valid create and invalid/missing-field cases

    def test_create_all_categories(self, client):
        """Every allowed category should succeed."""
        for cat in ("welfare", "cooling", "practical-assistance", "medical"):
            resp = client.post("/api/requests", json={
                "description": f"Test {cat}",
                "category": cat,
                "area": "Bolton"
            })
            assert resp.status_code == 201

    @pytest.mark.parametrize("field,value", [
        ("priority", "low"),
        ("priority", "medium"),
        ("priority", "high"),
        ("priority", "critical"),
        ("status", "new"),
        ("status", "in-progress"),
        ("status", "completed"),
    ])
    def test_create_all_enum_values(self, client, field, value):
        """Every allowed enum value for priority and status should succeed."""
        resp = client.post("/api/requests", json={
            "description": f"{field.title()} {value}",
            "category": "welfare",
            "area": "Bolton",
            field: value
        })
        assert resp.status_code == 201

    def test_create_case_insensitive_enum(self, client):
        """Enums should be case-insensitive (converted to lowercase)."""
        resp = client.post("/api/requests", json={
            "description": "Case test",
            "category": "Welfare",
            "area": "Bolton",
            "priority": "HIGH",
            "status": "New"
        })
        assert resp.status_code == 201
        assert resp.json["category"] == "welfare"
        assert resp.json["priority"] == "high"
        assert resp.json["status"] == "new"

    def test_create_trims_whitespace(self, client):
        data = {
            "description": "  Trim me  ",
            "category": " welfare ",
            "area": " Bolton "
        }
        resp = client.post("/api/requests", json=data)
        assert resp.status_code == 201
        assert resp.json["description"] == "Trim me"
        assert resp.json["category"] == "welfare"


# ======================================================================
# US04b — Update requests (Acceptance Criteria 1–4)
# ======================================================================

class TestUS04bUpdateRequests:
    """US04b: Implement update endpoint for existing request."""

    # --- AC item 1: Implement an update endpoint for an existing request

    def test_patch_single_field(self, client):
        create_resp = client.post("/api/requests", json={
            "description": "Original",
            "category": "welfare",
            "area": "Bolton"
        })
        req_id = create_resp.json["id"]

        resp = client.patch(f"/api/requests/{req_id}", json={"priority": "critical"})
        assert resp.status_code == 200
        assert resp.json["priority"] == "critical"

    def test_patch_multiple_fields(self, client):
        create_resp = client.post("/api/requests", json={
            "description": "Original",
            "category": "welfare",
            "area": "Bolton"
        })
        req_id = create_resp.json["id"]

        resp = client.patch(f"/api/requests/{req_id}", json={
            "priority": "high",
            "status": "in-progress"
        })
        assert resp.status_code == 200
        assert resp.json["priority"] == "high"
        assert resp.json["status"] == "in-progress"

    def test_patch_nonexistent_returns_404(self, client):
        resp = client.patch("/api/requests/9999", json={"status": "new"})
        assert resp.status_code == 404

    # --- AC item 2: Persist the changed fields in the database

    def test_patch_status_persists(self, client):
        create_resp = client.post("/api/requests", json={
            "description": "Persist test",
            "category": "welfare",
            "area": "Bolton"
        })
        req_id = create_resp.json["id"]

        client.patch(f"/api/requests/{req_id}", json={"status": "completed"})

        # Re-fetch from database via GET — confirms persistence.
        get_resp = client.get(f"/api/requests/{req_id}")
        assert get_resp.status_code == 200
        assert get_resp.json["status"] == "completed"

    def test_patch_priority_persists(self, client):
        create_resp = client.post("/api/requests", json={
            "description": "Persist priority",
            "category": "cooling",
            "area": "Manchester"
        })
        req_id = create_resp.json["id"]

        client.patch(f"/api/requests/{req_id}", json={"priority": "low"})

        get_resp = client.get(f"/api/requests/{req_id}")
        assert get_resp.json["priority"] == "low"

    # --- AC item 3: Retrieve the request and confirm the update is visible

    def test_update_retrieval_round_trip(self, client):
        """Full round-trip: create → patch → GET confirms all changes."""
        create_resp = client.post("/api/requests", json={
            "description": "Round trip original",
            "category": "medical",
            "area": "Liverpool"
        })
        req_id = create_resp.json["id"]

        # Patch several fields at once.
        client.patch(f"/api/requests/{req_id}", json={
            "description": "Updated description",
            "priority": "critical",
            "status": "in-progress"
        })

        get_resp = client.get(f"/api/requests/{req_id}")
        assert get_resp.status_code == 200
        assert get_resp.json["description"] == "Updated description"
        assert get_resp.json["priority"] == "critical"
        assert get_resp.json["status"] == "in-progress"

    def test_patch_does_not_affect_other_fields(self, client):
        """PATCH should only change supplied fields (partial update)."""
        create_resp = client.post("/api/requests", json={
            "description": "Original desc",
            "category": "welfare",
            "area": "Bolton",
            "priority": "low"
        })
        req_id = create_resp.json["id"]

        client.patch(f"/api/requests/{req_id}", json={"status": "completed"})

        get_resp = client.get(f"/api/requests/{req_id}")
        assert get_resp.json["description"] == "Original desc"
        assert get_resp.json["category"] == "welfare"
        assert get_resp.json["area"] == "bolton"
        assert get_resp.json["priority"] == "low"

    # --- AC item 4: Test the update path (and auth failure if already in scope)

    def test_patch_invalid_priority_returns_400(self, client):
        create_resp = client.post("/api/requests", json={
            "description": "Test", "category": "welfare", "area": "Bolton"
        })
        req_id = create_resp.json["id"]

        resp = client.patch(f"/api/requests/{req_id}", json={"priority": "urgent"})
        assert resp.status_code == 400

    def test_patch_invalid_status_returns_400(self, client):
        create_resp = client.post("/api/requests", json={
            "description": "Test", "category": "welfare", "area": "Bolton"
        })
        req_id = create_resp.json["id"]

        resp = client.patch(f"/api/requests/{req_id}", json={"status": "pending"})
        assert resp.status_code == 400

    def test_patch_invalid_category_returns_400(self, client):
        create_resp = client.post("/api/requests", json={
            "description": "Test", "category": "welfare", "area": "Bolton"
        })
        req_id = create_resp.json["id"]

        resp = client.patch(f"/api/requests/{req_id}", json={"category": "emergency"})
        assert resp.status_code == 400

    def test_patch_unknown_field_returns_400(self, client):
        create_resp = client.post("/api/requests", json={
            "description": "Test", "category": "welfare", "area": "Bolton"
        })
        req_id = create_resp.json["id"]

        resp = client.patch(f"/api/requests/{req_id}", json={"unknown_field": "value"})
        assert resp.status_code == 400
        assert "Cannot update" in resp.json["error"]

    def test_patch_empty_json_returns_400(self, client):
        create_resp = client.post("/api/requests", json={
            "description": "Test", "category": "welfare", "area": "Bolton"
        })
        req_id = create_resp.json["id"]

        resp = client.patch(f"/api/requests/{req_id}", json={})
        assert resp.status_code == 400

    def test_patch_empty_string_field_returns_400(self, client):
        create_resp = client.post("/api/requests", json={
            "description": "Test", "category": "welfare", "area": "Bolton"
        })
        req_id = create_resp.json["id"]

        resp = client.patch(f"/api/requests/{req_id}", json={"priority": ""})
        assert resp.status_code == 400

    def test_patch_case_insensitive_enum(self, client):
        """PATCH enums should also be case-insensitive."""
        create_resp = client.post("/api/requests", json={
            "description": "Test", "category": "welfare", "area": "Bolton"
        })
        req_id = create_resp.json["id"]

        resp = client.patch(f"/api/requests/{req_id}", json={"priority": "CRITICAL"})
        assert resp.status_code == 200
        assert resp.json["priority"] == "critical"

    def test_patch_description_and_area(self, client):
        create_resp = client.post("/api/requests", json={
            "description": "Old desc", "category": "welfare", "area": "Bolton"
        })
        req_id = create_resp.json["id"]

        resp = client.patch(f"/api/requests/{req_id}", json={
            "description": "New desc", "area": "Manchester"
        })
        assert resp.status_code == 200
        assert resp.json["description"] == "New desc"
        assert resp.json["area"] == "manchester"


# ======================================================================
# DELETE endpoint (Issue #7)
# ======================================================================

class TestDeleteRequests:
    """Basic tests for the DELETE /api/requests/<id> endpoint."""

    def test_delete_existing_returns_204(self, client):
        create_resp = client.post("/api/requests", json={
            "description": "To delete", "category": "welfare", "area": "Bolton"
        })
        req_id = create_resp.json["id"]

        resp = client.delete(f"/api/requests/{req_id}")
        assert resp.status_code == 204

    def test_delete_removes_from_database(self, client):
        create_resp = client.post("/api/requests", json={
            "description": "Gone soon", "category": "cooling", "area": "Manchester"
        })
        req_id = create_resp.json["id"]

        client.delete(f"/api/requests/{req_id}")
        get_resp = client.get(f"/api/requests/{req_id}")
        assert get_resp.status_code == 404

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete("/api/requests/9999")
        assert resp.status_code == 404
