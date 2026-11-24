"""Dashboard view – fetches data from the Flask API and renders metrics."""

import logging
import os

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


def index(request):
    """Render the staff dashboard with request metrics and centre availability."""

    # Fetch support requests from Flask API.
    requests_data = _get_json("/requests")

    # Count requests by status.
    total_requests = len(requests_data)
    new_count = sum(1 for r in requests_data if r.get("status") == "new")
    in_progress_count = sum(1 for r in requests_data if r.get("status") == "in progress")
    completed_count = sum(1 for r in requests_data if r.get("status") == "completed")
    outstanding_count = new_count + in_progress_count

    # Fetch cooling centres from Flask API.
    centres_data = _get_json("/centres")

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
    overall_utilisation = round((total_used / total_capacity * 100), 1) if total_capacity > 0 else 0.0

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
    }

    return render(request, "dashboard/index.html", context)
