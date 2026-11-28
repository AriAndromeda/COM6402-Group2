"""US08a – AI triage draft generation for support requests.

Drafts are produced via the US13 LLM adapter (mock by default). They are for
staff review only: never treat them as confirmed decisions, and never invent
missing resident details.
"""

from __future__ import annotations

import json
import re
from typing import Any

from llm_adapter import LlmAdapter, get_adapter

ALLOWED_PRIORITIES = ("low", "medium", "high", "critical")
ALLOWED_CATEGORIES = ("welfare", "cooling", "practical-assistance", "medical")

MIN_USEFUL_DESCRIPTION_LENGTH = 12
TRIAGE_PROMPT_MARKER = "HEATSHIELD_TRIAGE_JSON"

SUPPORT_OPTIONS = {
    "cooling": "Offer booking at a nearby cooling centre",
    "welfare": "Arrange a welfare check / wellbeing follow-up",
    "practical-assistance": (
        "Offer practical assistance (transport, supplies, or local support)"
    ),
    "medical": "Flag for clinical/medical pathway review (staff decision required)",
}


def _missing_fields(request_data: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in ("description", "category", "area"):
        value = request_data.get(field)
        if not isinstance(value, str) or not value.strip():
            missing.append(field)
    return missing


def _looks_incomplete(description: str, missing: list[str]) -> bool:
    if missing:
        return True
    return len(description.strip()) < MIN_USEFUL_DESCRIPTION_LENGTH


def _field_str(request_data: dict[str, Any], key: str) -> str:
    value = request_data.get(key)
    if not isinstance(value, str):
        return ""
    return value.strip()


def _heuristic_category(description: str, fallback: str) -> str:
    text = description.lower()
    if any(
        word in text for word in ("doctor", "medical", "ambulance", "chest pain")
    ):
        return "medical"
    if any(
        word in text
        for word in ("cool", "heat", "swelter", "temperature", "centre", "center")
    ):
        return "cooling"
    if any(
        word in text for word in ("food", "transport", "practical", "shopping", "fan")
    ):
        return "practical-assistance"
    if any(
        word in text
        for word in ("alone", "welfare", "check", "neighbour", "neighbor", "vulnerable")
    ):
        return "welfare"
    if fallback in ALLOWED_CATEGORIES:
        return fallback
    return "welfare"


def _heuristic_priority(description: str, fallback: str) -> str:
    """Infer priority from description; respect simple negations like 'not urgent'."""
    text = description.lower()

    # Negations first so "not urgent" does not become critical.
    if re.search(r"\bnot\s+urgent\b", text) or re.search(
        r"\bnot\s+an?\s+emergency\b", text
    ):
        if fallback in ALLOWED_PRIORITIES and fallback != "critical":
            return fallback
        return "medium"

    if any(
        word in text
        for word in ("urgent", "emergency", "cannot breathe", "collapse", "critical")
    ):
        return "critical"
    if any(word in text for word in ("high", "severe", "distressed", "unsafe")):
        return "high"
    if any(word in text for word in ("low", "minor", "when possible")):
        return "low"
    if fallback in ALLOWED_PRIORITIES:
        return fallback
    return "medium"


def _incomplete_draft(
    description: str,
    existing_category: str,
    existing_priority: str,
    missing: list[str],
) -> dict[str, Any]:
    category = (
        existing_category if existing_category in ALLOWED_CATEGORIES else "welfare"
    )
    priority = (
        existing_priority if existing_priority in ALLOWED_PRIORITIES else "medium"
    )
    summary = "Incomplete request: not enough reliable detail to finish triage."
    if description:
        summary = (
            f'Incomplete request based only on: "{description[:120]}". '
            "More information is needed before a firm recommendation."
        )
    return {
        "summary": summary,
        "category": category,
        "priority": priority,
        "rationale": (
            "One or more required fields are missing or the description is too "
            "short. No extra personal or medical details were invented."
        ),
        "support_option": (
            "Ask the resident/staff for more information before acting"
        ),
        "incomplete": True,
        "missing_fields": missing,
        "draft": True,
        "status": "pending_review",
        "applied": False,
    }


def _structured_draft_from_fields(request_data: dict[str, Any]) -> dict[str, Any]:
    """Deterministic structured draft used for adapter mock / JSON parse fallback."""
    description = _field_str(request_data, "description")
    area = _field_str(request_data, "area")
    existing_category = _field_str(request_data, "category").lower()
    existing_priority = _field_str(request_data, "priority").lower()
    missing = _missing_fields(request_data)

    if _looks_incomplete(description, missing):
        return _incomplete_draft(
            description, existing_category, existing_priority, missing
        )

    category = _heuristic_category(description, existing_category)
    priority = _heuristic_priority(description, existing_priority)
    area_bit = f" in {area}" if area else ""
    return {
        "summary": f"Heat Shield case{area_bit}: {description[:180]}",
        "category": category,
        "priority": priority,
        "rationale": (
            "Structured draft produced via the Heat Shield LLM adapter "
            f"(category cue → {category}, priority cue → {priority}). "
            "Based only on supplied fictional request fields."
        ),
        "support_option": SUPPORT_OPTIONS.get(
            category, "Review manually with a staff supervisor"
        ),
        "incomplete": False,
        "missing_fields": [],
        "draft": True,
        "status": "pending_review",
        "applied": False,
    }


def mock_triage_completion_text(prompt: str) -> str:
    """JSON completion text for the US13 mock adapter on triage prompts."""
    # Pull the fictional description block out of the prompt when present.
    match = re.search(
        r"Description:\s*(.*?)\nCategory:",
        prompt,
        flags=re.IGNORECASE | re.DOTALL,
    )
    description = match.group(1).strip() if match else ""
    cat_match = re.search(r"Category:\s*(.*)", prompt, flags=re.IGNORECASE)
    area_match = re.search(r"Area:\s*(.*)", prompt, flags=re.IGNORECASE)
    pri_match = re.search(r"Priority:\s*(.*)", prompt, flags=re.IGNORECASE)
    request_data = {
        "description": description,
        "category": cat_match.group(1).strip() if cat_match else "",
        "area": area_match.group(1).strip() if area_match else "",
        "priority": pri_match.group(1).strip() if pri_match else "",
    }
    draft = _structured_draft_from_fields(request_data)
    return json.dumps(
        {
            "summary": draft["summary"],
            "category": draft["category"],
            "priority": draft["priority"],
            "rationale": draft["rationale"],
            "support_option": draft["support_option"],
        }
    )


def _build_triage_prompt(request_data: dict[str, Any]) -> str:
    description = _field_str(request_data, "description")
    category = _field_str(request_data, "category")
    area = _field_str(request_data, "area")
    priority = _field_str(request_data, "priority")
    return (
        f"{TRIAGE_PROMPT_MARKER}\n"
        "Return JSON only with keys summary, category, priority, rationale, "
        "support_option. Use only the fictional Heat Shield fields below. "
        "Do not invent personal identities or medical history. "
        f"category must be one of {list(ALLOWED_CATEGORIES)}. "
        f"priority must be one of {list(ALLOWED_PRIORITIES)}.\n"
        f"Description: {description}\n"
        f"Category: {category}\n"
        f"Area: {area}\n"
        f"Priority: {priority}\n"
    )


def _parse_triage_json(text: str) -> dict[str, Any] | None:
    if not isinstance(text, str) or not text.strip():
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    required = ("summary", "category", "priority", "rationale", "support_option")
    if any(not isinstance(data.get(key), str) or not data.get(key).strip() for key in required):
        return None
    category = data["category"].strip().lower()
    priority = data["priority"].strip().lower()
    if category not in ALLOWED_CATEGORIES or priority not in ALLOWED_PRIORITIES:
        return None
    return {
        "summary": data["summary"].strip(),
        "category": category,
        "priority": priority,
        "rationale": data["rationale"].strip(),
        "support_option": data["support_option"].strip(),
    }


def generate_triage_draft(
    request_data: dict[str, Any],
    adapter: LlmAdapter | None = None,
) -> dict[str, Any]:
    """Build a structured triage draft via the LLM adapter.

    Incomplete inputs are flagged without inventing details. Complete inputs
    call the US13 adapter; mock/live metadata on the response comes from that
    adapter call (not from a separate rules-only path pretending to be live).
    """
    if not isinstance(request_data, dict):
        raise ValueError("request_data must be an object")

    llm = adapter or get_adapter()
    missing = _missing_fields(request_data)
    description = _field_str(request_data, "description")
    existing_category = _field_str(request_data, "category").lower()
    existing_priority = _field_str(request_data, "priority").lower()

    if _looks_incomplete(description, missing):
        draft = _incomplete_draft(
            description, existing_category, existing_priority, missing
        )
        status = llm.public_status()
        draft.update(
            {
                "provider": status.get("provider", "mock"),
                "mode": "mock",
                "model": status.get("model", "mock"),
                "simulated": True,
                "is_live": False,
                "generation_path": "incomplete_guard",
            }
        )
        return draft

    prompt = _build_triage_prompt(request_data)
    llm_result = llm.generate(prompt)
    parsed = _parse_triage_json(llm_result.get("text", ""))

    if parsed is None:
        draft = _structured_draft_from_fields(request_data)
        generation_path = "llm_adapter_structured_fallback"
    else:
        draft = {
            **parsed,
            "incomplete": False,
            "missing_fields": [],
            "draft": True,
            "status": "pending_review",
            "applied": False,
        }
        generation_path = "llm_adapter_json"

    draft.update(
        {
            "provider": llm_result.get("provider"),
            "mode": llm_result.get("mode"),
            "model": llm_result.get("model"),
            "simulated": bool(llm_result.get("simulated")),
            "is_live": bool(llm_result.get("is_live")),
            "generation_path": generation_path,
        }
    )
    if llm_result.get("fallback_reason"):
        draft["fallback_reason"] = llm_result["fallback_reason"]
    return draft
