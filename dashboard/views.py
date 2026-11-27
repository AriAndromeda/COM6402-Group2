"""Dashboard view – fetches data from the Flask API and renders metrics."""

import logging
import os
import re
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

logger = logging.getLogger(__name__)
ALLOWED_REQUEST_STATUSES = ("new", "in progress", "completed")

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

@login_required
def index(request):
    """Render the searchable Heat Shield dashboard for authorised staff."""
    if not request.user.groups.filter(
        name="Heat Shield Staff"
    ).exists():
        raise PermissionDenied(
            "You are not authorised to access the Heat Shield dashboard."
        )
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
    if not isinstance(all_requests, list):
        all_requests = []

    # Queue: reuse the full list when no Flask filters are set (avoid a second fetch).
    api_filters = any(
        isinstance(value, str) and value.strip()
        for value in (status, priority, area)
    )
    if api_filters:
        queue_path = _requests_path(status=status, priority=priority, area=area)
        requests_data = _get_json(queue_path)
        if not isinstance(requests_data, list):
            requests_data = []
    else:
        requests_data = list(all_requests)

    # Optional free-text search is applied in-process after the API result.
    requests_data = _apply_search(requests_data, search_query)

    # Count requests by status (from full dataset).
    total_requests = len(all_requests)
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


def get_staff_api_token(user):
    """Retrieve a staff-specific API credential from the environment."""

    if not user.is_authenticated or not user.is_active:
        return None

    if not user.groups.filter(
        name="Heat Shield Staff"
    ).exists():
        return None

    # Require canonical usernames to avoid ambiguous mappings.
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", user.username):
        return None

    variable_name = (
        f"HEATSHIELD_API_TOKEN_{user.username.upper()}"
    )

    return os.environ.get(variable_name)

def update_request_status(user, request_id, new_status):
    """Update a support request through the authenticated Flask API."""

    if new_status not in ALLOWED_REQUEST_STATUSES:
        return False, "Invalid request status."

    token = get_staff_api_token(user)

    if not token:
        return False, "Staff API authorisation is unavailable."

    try:
        response = requests.patch(
            f"{API_BASE}/requests/{request_id}",
            json={"status": new_status},
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )

    except requests.RequestException:
        logger.exception("Flask API status update failed")
        return False, "Unable to contact the support request service."

    if response.status_code == 200:
        return True, "Request status updated successfully."

    if response.status_code in (401, 403):
        return False, "You are not authorised to update this request."

    if response.status_code == 404:
        return False, "Support request not found."

    if response.status_code == 400:
        return False, "The requested status was rejected."

    return False, "Unable to update the request."


@login_required
def request_detail(request, request_id):
    """Display and update a support request for authorised staff."""

    if not request.user.groups.filter(
        name="Heat Shield Staff"
    ).exists():
        raise PermissionDenied(
            "You are not authorised to manage support requests."
        )

    error_message = None

    if request.method == "POST":
        new_status = request.POST.get("status", "").strip()

        success, message = update_request_status(
            request.user,
            request_id,
            new_status,
        )

        if success:
            return redirect(
                "dashboard:request_detail",
                request_id=request_id,
            )

        error_message = message

    support_request = _get_json(f"/requests/{request_id}")

    if not isinstance(support_request, dict):
        raise Http404("Support request not found")

    context = {
        "support_request": support_request,
        "allowed_statuses": ALLOWED_REQUEST_STATUSES,
        "error_message": error_message,
    }

    return render(
        request,
        "dashboard/request_detail.html",
        context,
    )
