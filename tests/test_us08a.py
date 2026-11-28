"""US08a – AI triage draft generation via the US13 LLM adapter."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app import SupportRequest, db
from llm_adapter import LlmAdapter, LlmConfig, get_adapter
from triage import generate_triage_draft


def _create_request(
    *,
    description="Elderly resident in Bolton needs a cool space during the heatwave",
    category="cooling",
    area="Bolton",
    priority="medium",
    status="new",
):
    row = SupportRequest(
        description=description,
        category=category,
        area=area,
        priority=priority,
        status=status,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.session.add(row)
    db.session.commit()
    return row


@pytest.fixture(autouse=True)
def _clear_adapter_cache():
    get_adapter.cache_clear()
    yield
    get_adapter.cache_clear()


class TestTriageDraftHelper:
    def test_structured_fields_present_for_complete_request(self):
        draft = generate_triage_draft(
            {
                "description": (
                    "Resident feels unsafe in the heat and needs a cooling centre"
                ),
                "category": "cooling",
                "area": "Bolton",
                "priority": "medium",
            },
            adapter=LlmAdapter(LlmConfig(provider="mock")),
        )
        assert draft["draft"] is True
        assert draft["applied"] is False
        assert draft["status"] == "pending_review"
        assert draft["incomplete"] is False
        assert draft["provider"] == "mock"
        assert draft["mode"] == "mock"
        assert draft["simulated"] is True
        assert draft["is_live"] is False
        assert draft["generation_path"] == "llm_adapter_json"
        assert draft["category"] in {
            "welfare",
            "cooling",
            "practical-assistance",
            "medical",
        }
        assert draft["priority"] in {"low", "medium", "high", "critical"}
        assert draft["summary"]
        assert draft["rationale"]
        assert draft["support_option"]

    def test_uses_llm_adapter_generate(self):
        adapter = MagicMock(spec=LlmAdapter)
        adapter.generate.return_value = {
            "provider": "mock",
            "mode": "mock",
            "model": "mock",
            "simulated": True,
            "is_live": False,
            "text": (
                '{"summary":"Heat case","category":"cooling","priority":"high",'
                '"rationale":"heat cues","support_option":"Offer cooling centre"}'
            ),
        }
        draft = generate_triage_draft(
            {
                "description": "Needs cooling during heatwave in Farnworth",
                "category": "cooling",
                "area": "Farnworth",
                "priority": "medium",
            },
            adapter=adapter,
        )
        adapter.generate.assert_called_once()
        prompt = adapter.generate.call_args.args[0]
        assert "HEATSHIELD_TRIAGE_JSON" in prompt
        assert draft["generation_path"] == "llm_adapter_json"
        assert draft["provider"] == "mock"
        assert draft["category"] == "cooling"
        assert draft["priority"] == "high"

    def test_incomplete_request_does_not_invent_details(self):
        adapter = MagicMock(spec=LlmAdapter)
        adapter.public_status.return_value = {
            "provider": "mock",
            "model": "mock",
            "mode": "mock",
        }
        draft = generate_triage_draft(
            {
                "description": "help",
                "category": "cooling",
                "area": "Bolton",
                "priority": "medium",
            },
            adapter=adapter,
        )
        adapter.generate.assert_not_called()
        assert draft["incomplete"] is True
        assert draft["applied"] is False
        assert draft["generation_path"] == "incomplete_guard"
        assert draft["simulated"] is True
        banned = ("john", "nhs number", "diagnosed", "made up")
        blob = " ".join(
            [draft["summary"], draft["rationale"], draft["support_option"]]
        ).lower()
        assert not any(word in blob for word in banned)
        assert "more information" in draft["support_option"].lower()

    def test_missing_required_fields_flagged(self):
        adapter = MagicMock(spec=LlmAdapter)
        adapter.public_status.return_value = {
            "provider": "mock",
            "model": "mock",
            "mode": "mock",
        }
        draft = generate_triage_draft(
            {"description": "", "category": "", "area": ""},
            adapter=adapter,
        )
        assert draft["incomplete"] is True
        assert "description" in draft["missing_fields"]
        assert "category" in draft["missing_fields"]
        assert "area" in draft["missing_fields"]

    def test_not_urgent_is_not_treated_as_critical(self):
        draft = generate_triage_draft(
            {
                "description": (
                    "Resident needs a cooling centre but this is not urgent"
                ),
                "category": "cooling",
                "area": "Bolton",
                "priority": "medium",
            },
            adapter=LlmAdapter(LlmConfig(provider="mock")),
        )
        assert draft["priority"] != "critical"
        assert draft["priority"] in {"low", "medium", "high"}

    def test_medical_and_practical_branches(self):
        medical = generate_triage_draft(
            {
                "description": "Chest pain and needs a doctor during the heatwave",
                "category": "welfare",
                "area": "Bolton",
                "priority": "medium",
            },
            adapter=LlmAdapter(LlmConfig(provider="mock")),
        )
        assert medical["category"] == "medical"

        practical = generate_triage_draft(
            {
                "description": (
                    "Needs transport and food shopping help for daily living"
                ),
                "category": "welfare",
                "area": "Horwich",
                "priority": "medium",
            },
            adapter=LlmAdapter(LlmConfig(provider="mock")),
        )
        assert practical["category"] == "practical-assistance"

    def test_welfare_low_priority_and_fallback_category(self):
        welfare = generate_triage_draft(
            {
                "description": (
                    "Vulnerable neighbour is alone and needs a welfare check soon"
                ),
                "category": "cooling",
                "area": "Bolton",
                "priority": "medium",
            },
            adapter=LlmAdapter(LlmConfig(provider="mock")),
        )
        assert welfare["category"] == "welfare"

        low = generate_triage_draft(
            {
                "description": (
                    "Minor heat discomfort, low priority when possible please"
                ),
                "category": "cooling",
                "area": "Bolton",
                "priority": "high",
            },
            adapter=LlmAdapter(LlmConfig(provider="mock")),
        )
        assert low["priority"] == "low"

        fallback = generate_triage_draft(
            {
                "description": (
                    "General assistance request with enough detail for triage"
                ),
                "category": "practical-assistance",
                "area": "Bolton",
                "priority": "medium",
            },
            adapter=LlmAdapter(LlmConfig(provider="mock")),
        )
        assert fallback["category"] == "practical-assistance"

    def test_invalid_request_data_raises(self):
        with pytest.raises(ValueError, match="request_data must be an object"):
            generate_triage_draft("not-a-dict")  # type: ignore[arg-type]

    def test_malformed_adapter_json_uses_structured_fallback(self):
        adapter = MagicMock(spec=LlmAdapter)
        adapter.generate.return_value = {
            "provider": "mock",
            "mode": "mock",
            "model": "mock",
            "simulated": True,
            "is_live": False,
            "text": "not-json-at-all",
        }
        draft = generate_triage_draft(
            {
                "description": "Needs a cool space during the heatwave today",
                "category": "cooling",
                "area": "Bolton",
                "priority": "medium",
            },
            adapter=adapter,
        )
        assert draft["generation_path"] == "llm_adapter_structured_fallback"
        assert draft["provider"] == "mock"
        assert draft["simulated"] is True
        assert draft["draft"] is True


class TestTriageEndpoint:
    def test_requires_staff_auth(self, client):
        row = _create_request()
        resp = client.post(f"/api/requests/{row.id}/triage")
        assert resp.status_code == 401

    def test_generates_draft_for_staff(self, client, staff_headers):
        row = _create_request()
        resp = client.post(
            f"/api/requests/{row.id}/triage",
            headers=staff_headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["draft"] is True
        assert body["applied"] is False
        assert body["request_unchanged"] is True
        assert body["status"] == "pending_review"
        assert body["provider"] == "mock"
        assert body["mode"] == "mock"
        assert body["simulated"] is True
        assert body["generation_path"] == "llm_adapter_json"
        suggestion = body["suggestion"]
        for key in (
            "summary",
            "category",
            "priority",
            "rationale",
            "support_option",
        ):
            assert key in suggestion
            assert suggestion[key]

    def test_does_not_auto_change_stored_request(self, client, staff_headers):
        row = _create_request(
            description="Urgent: vulnerable neighbour is unsafe in severe heat",
            category="welfare",
            priority="low",
            status="new",
        )
        before = {
            "description": row.description,
            "category": row.category,
            "priority": row.priority,
            "status": row.status,
            "area": row.area,
        }

        resp = client.post(
            f"/api/requests/{row.id}/triage",
            headers=staff_headers,
        )
        assert resp.status_code == 200
        suggestion = resp.get_json()["suggestion"]
        assert suggestion["draft"] is True
        assert suggestion["applied"] is False

        db.session.refresh(row)
        assert row.description == before["description"]
        assert row.category == before["category"]
        assert row.priority == before["priority"]
        assert row.status == before["status"]
        assert row.area == before["area"]

        get_resp = client.get(f"/api/requests/{row.id}")
        assert get_resp.status_code == 200
        stored = get_resp.get_json()
        assert stored["category"] == before["category"]
        assert stored["priority"] == before["priority"]
        assert stored["status"] == before["status"]

    def test_incomplete_request_endpoint(self, client, staff_headers):
        row = _create_request(description="?", category="cooling", area="Bolton")
        resp = client.post(
            f"/api/requests/{row.id}/triage",
            headers=staff_headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["suggestion"]["incomplete"] is True
        assert body["applied"] is False
        assert body["generation_path"] == "incomplete_guard"
        assert body["simulated"] is True

        db.session.refresh(row)
        assert row.description == "?"
        assert row.category == "cooling"

    def test_unknown_request_returns_404(self, client, staff_headers):
        resp = client.post("/api/requests/99999/triage", headers=staff_headers)
        assert resp.status_code == 404
