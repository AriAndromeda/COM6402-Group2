# HeatShield – API Documentation

## Overview

The HeatShield API provides endpoints for managing support
requests and retrieving information about cooling centres
and bookings.

The API uses JSON for data exchange.

Base URL: http://127.0.0.1:5000

## 1. Health Check

Endpoint: GET /api/health

Purpose:
Check whether the Flask API is responding.

Successful response (200 OK):

```json
{
  "status": "ok"
}
```

## 2. List and Filter Support Requests

Endpoint: GET /api/requests

Purpose:
Retrieve support requests, optionally filtered by
category, status, priority or area.

Supported query parameters:

| Parameter | Description | Example |
|-----------|-------------|---------|
| category | Support request category | welfare |
| status | Current request status | new |
| priority | Request priority | high |
| area | Geographical area | Bolton |

Example:

GET /api/requests?category=welfare&priority=high&area=Bolton

Successful response (200 OK):

[
  {
    "id": 1,
    "description": "Water assistance needed",
    "category": "welfare",
    "area": "Bolton",
    "priority": "high",
    "status": "new"
  }
]

When no records match, the API returns an empty JSON list.

Area filtering is case-insensitive.

## 3. Create a Support Request

Endpoint: POST /api/requests

Required JSON fields:
- description
- category
- area

Optional fields:
- priority (default: medium)
- status (default: new)

Example request:

{
  "description": "Water assistance needed",
  "category": "welfare",
  "area": "Bolton",
  "priority": "high",
  "status": "new"
}

Successful response:
201 Created – Returns the newly created support request.

Invalid request:
400 Bad Request – Returns a JSON error message.

## 4. Retrieve a Support Request

Endpoint: GET /api/requests/{id}

200 OK – Returns the matching support request.

404 Not Found – Request does not exist.

## 5. Update a Support Request

Endpoint: PATCH /api/requests/{id}

Purpose:
Update one or more fields of an existing request.

Example JSON body:

{
  "priority": "high",
  "status": "in progress"
}

200 OK – Returns the updated support request.

400 Bad Request – Invalid update information.

404 Not Found – Request does not exist.

## 6. Delete a Support Request

Endpoint: DELETE /api/requests/{id}

204 No Content – Request deleted successfully.

404 Not Found – Request does not exist.

## 7. Cooling Centre Endpoints

### 7.1 Create a Cooling Centre

Endpoint: POST /api/centres

Required fields:
- name: Name of the cooling centre.
- area: Geographical location.
- capacity: Positive integer representing total capacity.

Optional fields:
- opening_hours: Opening hours (defaults to an empty string).
- status: Centre status (defaults to open).

Successful response:
201 Created – Returns the newly created cooling centre.

Invalid request:
400 Bad Request – Returns a JSON error message.

### 7.2 Retrieve All Cooling Centres

Endpoint: GET /api/centres

Successful response:
200 OK – Returns a JSON list of cooling centres.

An empty list is returned when no centres exist.

### 7.3 Retrieve a Cooling Centre by ID

Endpoint: GET /api/centres/{id}

Successful response:
200 OK – Returns the requested cooling centre.

Not found:
404 Not Found – Returns a JSON error message.

## 8. Booking Endpoints

POST /api/bookings
Create a booking (201 Created).

GET /api/bookings/{id}
Retrieve a booking (200 OK or 404 Not Found).

Booking requests include:
- request_id
- centre_id
- booking_date
- booking_time
- spaces_required

The API returns 409 Conflict when the centre is closed
or insufficient spaces are available.

## 9. Validation and Filtering Rules

### Supported Values

Category:
- welfare
- cooling
- practical-assistance
- medical

Priority:
- low
- medium
- high
- critical

Status:
- new
- in progress
- completed

### Field Constraints

- Description: required, maximum 500 characters.
- Area: required, maximum 80 characters.
- Category: required and must use a supported value.
- Priority: optional when creating a request;
  defaults to medium.
- Status: optional when creating a request;
  defaults to new.

### Filtering Behaviour

- Multiple filters are combined using AND logic.
- Area filtering is case-insensitive.
- Category, status and priority matching is
  case-sensitive.
- Results are ordered by request ID.
- Searches with no matches return 200 OK and [].
- Unrecognised query parameters are ignored.
- Unsupported filter values currently return
  an empty list rather than a validation error.
- Empty filter values are ignored.

### Health-Check Limitations

GET /api/health returns:

{
  "status": "ok"
}

This confirms that the Flask application responds.

It does not verify database connectivity,
database integrity or external service availability.

## 10. LLM Adapter (US13 – Sprint 1 attempt)

Configurable adapter for mock or OpenAI-compatible providers.
Credentials are read from environment variables and are never
returned in API responses.

**Privacy:** Only fictional Heat Shield case text may be sent to an
external LLM. Do not submit real personal or confidential records.
Live external calls also require `HEATSHIELD_LLM_ALLOW_EXTERNAL=true`.

Environment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| HEATSHIELD_LLM_PROVIDER | `mock` or `openai` | `mock` |
| HEATSHIELD_LLM_API_KEY | Provider API key (keep secret) | empty |
| HEATSHIELD_LLM_MODEL | Model name for live provider | `gpt-4o-mini` |
| HEATSHIELD_LLM_BASE_URL | OpenAI-compatible base URL | `https://api.openai.com/v1` |
| HEATSHIELD_LLM_ALLOW_EXTERNAL | Must be `true` to enable live provider calls | `false` |

### Status

Endpoint: GET /api/llm/status

Successful response (200 OK):

```json
{
  "provider": "mock",
  "model": "mock",
  "configured": true,
  "mode": "mock",
  "allow_external": false,
  "privacy_note": "Only fictional Heat Shield case text may be sent to external LLM providers. Set HEATSHIELD_LLM_ALLOW_EXTERNAL=true to enable live calls."
}
```

### Generate

Endpoint: POST /api/llm/generate

Requires staff Bearer authentication (`Authorization: Bearer <token>`).

Required JSON field: `prompt` (non-empty, maximum 2000 characters).

Example:

```json
{ "prompt": "What advice should staff give during a heatwave?" }
```

Successful response (200 OK) returns `provider`, `mode`, `model`,
`simulated`, `is_live` and `text`.

On rate limits, timeouts, provider errors, or when external calls are
disabled, the adapter falls back to mock mode. Fallback responses set
`simulated` to true, include `fallback_reason`, and prefix `text` with
`[SIMULATED / MOCK FALLBACK]` so mock output is never mistaken for a
live model reply.

## 11. Running Automated Tests

Install dependencies:

python -m pip install -r requirements.txt

Run all automated tests:

python -m pytest tests/ -v

Run US05 tests only:

python -m pytest tests/test_us05.py -v

Run US13 tests only:

python -m pytest tests/test_us13.py -v

## 12. Limitations

This is a local development API.

Only fictional information should be used.
The LLM adapter defaults to mock mode for local demos;
live providers require a secret API key in the environment.

Further validation, integration and security testing
will be required before production deployment.