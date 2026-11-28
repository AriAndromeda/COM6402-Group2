"""US08a – AI triage draft generation for support requests.

Produces structured *draft* suggestions for staff review. Drafts must never
be treated as confirmed decisions and must not invent missing resident details.
"""

from __future__ import annotations

from typing import Any

ALLOWED_PRIORITIES = ("low", "medium", "high", "critical")
ALLOWED_CATEGORIES = ("welfare", "cooling", "practical-assistance", "medical")

MIN_USEFUL_DESCRIPTION_LENGTH = 12

SUPPORT_OPTIONS = {
    "cooling": "Offer booking at a nearby cooling centre",
    "welfare": "Arrange a welfare check / wellbeing follow-up",
    "practical-assistance": "Offer practical assistance (transport, supplies, or local support)",
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


def _heuristic_category(description: str, fallback: str) -> str:
    text = description.lower()
    if any(word in text for word in ("doctor", "medical", "ambulance", "chest pain")):
        return "medical"
    if any(word in text for word in ("cool", "heat", "swelter", "temperature", "centre", "center")):
        return "cooling"
    if any(word in text for word in ("food", "transport", "practical", "shopping", "fan")):
        return "practical-assistance"
    if any(word in text for word in ("alone", "welfare", "check", "neighbour", "neighbor", "vulnerable")):
        return "welfare"
    if fallback in ALLOWED_CATEGORIES:
        return fallback
    return "welfare"


def _heuristic_priority(description: str, fallback: str) -> str:
    text = description.lower()
    if any(word in text for word in ("urgent", "emergency", "cannot breathe", "collapse", "critical")):
        return "critical"
    if any(word in text for word in ("high", "severe", "distressed", "unsafe")):
        return "high"
    if any(word in text for word in ("low", "minor", "when possible")):
        return "low"
    if fallback in ALLOWED_PRIORITIES:
        return fallback
    return "medium"


def generate_triage_draft(request_data: dict[str, Any]) -> dict[str, Any]:
    """Build a structured triage draft from fictional request fields only.

    Incomplete inputs are flagged. The draft must not invent personal facts
    that were not present in the request payload.
    """
    if not isinstance(request_data, dict):
        raise ValueError("request_data must be an object")

    missing = _missing_fields(request_data)
    description = (
        request_data.get("description")
        if isinstance(request_data.get("description"), str)
        else ""
    ).strip()
    area = (
        request_data.get("area")
        if isinstance(request_data.get("area"), str)
        else ""
    ).strip()
    existing_category = (
        request_data.get("category")
        if isinstance(request_data.get("category"), str)
        else ""
    ).strip().lower()
    existing_priority = (
        request_data.get("priority")
        if isinstance(request_data.get("priority"), str)
        else ""
    ).strip().lower()

    incomplete = _looks_incomplete(description, missing)

    if incomplete:
        category = (
            existing_category
            if existing_category in ALLOWED_CATEGORIES
            else "welfare"
        )
        priority = (
            existing_priority
            if existing_priority in ALLOWED_PRIORITIES
            else "medium"
        )
        summary = (
            "Incomplete request: not enough reliable detail to finish triage."
        )
        if description:
            summary = (
                f"Incomplete request based only on: \"{description[:120]}\". "
                "More information is needed before a firm recommendation."
            )
        rationale = (
            "One or more required fields are missing or the description is too "
            "short. No extra personal or medical details were invented."
        )
        support_option = "Ask the resident/staff for more information before acting"
    else:
        category = _heuristic_category(description, existing_category)
        priority = _heuristic_priority(description, existing_priority)
        area_bit = f" in {area}" if area else ""
        summary = f"Heat Shield case{area_bit}: {description[:180]}"
        rationale = (
            f"Suggested from the supplied description only "
            f"(category cue → {category}, priority cue → {priority})."
        )
        support_option = SUPPORT_OPTIONS.get(
            category, "Review manually with a staff supervisor"
        )

    return {
        "summary": summary,
        "category": category,
        "priority": priority,
        "rationale": rationale,
        "support_option": support_option,
        "incomplete": incomplete,
        "missing_fields": missing,
        "draft": True,
        "status": "pending_review",
        "applied": False,
    }
