"""Validation constants and helpers shared across controllers."""

# Allowed values for enumerated fields (US04a validation).
ALLOWED_PRIORITIES = ("low", "medium", "high", "critical")
ALLOWED_STATUSES = ("new", "in progress", "completed")
ALLOWED_CATEGORIES = ("welfare", "cooling", "practical-assistance", "medical")

# Field length limits (mirrors model columns for client-side validation).
MAX_DESCRIPTION_LENGTH = 500
MAX_AREA_LENGTH = 80

# Mapping of enum fields to their allowed values — single source of truth.
ENUM_FIELDS = {
    "category": ALLOWED_CATEGORIES,
    "priority": ALLOWED_PRIORITIES,
    "status": ALLOWED_STATUSES,
}


def validate_enum(value, field_name, allowed):
    """Return (cleaned_value, error_msg)."""
    if not isinstance(value, str) or not value.strip():
        return None, f"{field_name} is required"
    cleaned = value.strip().lower()
    if cleaned not in allowed:
        return None, (
            f"{field_name} must be one of: " + ", ".join(sorted(allowed))
        )
    return cleaned, None
