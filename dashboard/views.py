"""Dashboard view – fetches data from the Flask API and renders metrics."""

import logging
import os
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.shortcuts import render

logger = logging.getLogger(__name__)

# Base URL for the Flask backend API (readable via DJANGO_FLASK_API_URL env var).
API_BASE = os.environ.get(
    "DJANGO_FLASK_API_URL",
    getattr(settings, "FLASK_API_URL", "http://127.0.0.1:5000/api"),
)


def _get_json(path):
    """Fetch JSON from the Flask API, or return an empty list on failure."""
    try:
        resp = requests.get(f"{API_BASE}{path}", timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except (requests.RequestException, ValueError):
        logger.warning("Flask API unreachable at %s%s", API_BASE, path)
    return []


def _requests_path(status="", priority="", area="", category=""):
    """Build /requests path with optional Flask filter query params (US07b)."""
    params = {}
    for key, value in (
        ("status", status),
        ("priority", priority),
        ("area", area),
        ("category", category),
    ):
        if isinstance(value, str) and value.strip():
            params[key] = value.strip()
    if not params:
        return "/requests"
    return f"/requests?{urlencode(params)}"


def _apply_search(requests_data, query):
    """Filter requests whose description contains the search text (case-insensitive)."""
    if not isinstance(query, str) or not query.strip():
        return requests_data
    needle = query.strip().lower()
    return [
        row
        for row in requests_data
        if needle in str(row.get("description", "")).lower()
        or needle == str(row.get("id", ""))
    ]


def index(request):
    """Render the staff dashboard with request metrics and centre availability.

    .. note::
       Authentication is not implemented yet (see US08). Anyone who can reach
       this URL sees all support-request data. Add auth before any deployment.
    """

    # US07b filter / search inputs (GET form on the dashboard).
    status = request.GET.get("status", "")
    priority = request.GET.get("priority", "")
    area = request.GET.get("area", "")
    search_query = request.GET.get("q", "")
    filters_active = any(
        isinstance(value, str) and value.strip()
        for value in (status, priority, area, search_query)
    )

    # Metrics stay based on the full queue (US07a behaviour).
    all_requests = _get_json("/requests")

    # Queue list uses Flask filters, then optional description search.
    queue_path = _requests_path(status=status, priority=priority, area=area)
    requests_data = _get_json(queue_path)
    if not isinstance(requests_data, list):
        requests_data = []
    requests_data = _apply_search(requests_data, search_query)

    # Count requests by status (from full dataset).
    total_requests = len(all_requests) if isinstance(all_requests, list) else 0
    new_count = sum(1 for r in all_requests if r.get("status") == "new")
    in_progress_count = sum(
        1 for r in all_requests if r.get("status") == "in progress"
    )
    completed_count = sum(1 for r in all_requests if r.get("status") == "completed")
    outstanding_count = new_count + in_progress_count

    # Fetch cooling centres from Flask API.
    centres_data = _get_json("/centres")
    if not isinstance(centres_data, list):
        centres_data = []

    # Build centre availability list with capacity info.
    centres = []
    total_capacity = 0
    total_available = 0
    for c in centres_data:
        capacity = c.get("capacity", 0)
        available = c.get("spaces_available", 0)
        used = capacity - available
        utilisation = (used / capacity * 100) if capacity > 0 else 0
        total_capacity += capacity
        total_available += available
        centres.append({
            "id": c.get("id"),
            "name": c.get("name", ""),
            "area": c.get("area", ""),
            "capacity": capacity,
            "spaces_available": available,
            "opening_hours": c.get("opening_hours", ""),
            "status": c.get("status", ""),
            "utilisation_pct": round(utilisation, 1),
        })

    # Compute overall utilisation percentage.
    total_used = total_capacity - total_available
    overall_utilisation = (
        round((total_used / total_capacity * 100), 1) if total_capacity > 0 else 0.0
    )

    context = {
        "total_requests": total_requests,
        "outstanding_count": outstanding_count,
        "new_count": new_count,
        "in_progress_count": in_progress_count,
        "completed_count": completed_count,
        "requests_data": requests_data,
        "centres": centres,
        "total_capacity": total_capacity,
        "total_available": total_available,
        "overall_utilisation_pct": overall_utilisation,
        # US07b form state
        "filter_status": status,
        "filter_priority": priority,
        "filter_area": area,
        "search_query": search_query,
        "filters_active": filters_active,
    }

    return render(request, "dashboard/index.html", context)
