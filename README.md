# Heat Shield – COM6402 Group 2

A staff dashboard for managing cooling-centre support requests. The application consists of a **Flask REST API** that serves data and a **Django web dashboard** that displays live metrics to staff.

## Architecture

```
┌──────────────┐        HTTP GET         ┌──────────────┐
│  Django      │ ──────────────────────► │  Flask       │
│  Dashboard   │                         │  REST API    │
│  (:8000)     │                         │  (:5000)     │
└──────────────┘                         └──────────────┘
```

- **Flask API** – SQLite-backed CRUD for support requests, cooling centres, and bookings. Runs on port `5000` (falls back to `5001` if occupied).
- **Django Dashboard** – Fetches live data from the Flask API via HTTP and renders metric cards, request tables, and centre availability with utilisation bars. Runs on port `8000`.

## Features

### Flask REST API (`app.py`)

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Health check – returns `{"status": "ok"}` |
| `/api/requests` | GET | List all support requests (filterable by `category`, `area`, `priority`, `status`) |
| `/api/requests/<id>` | GET / PATCH / DELETE | Get, update, or delete a single request |
| `/api/centres` | GET / POST | List centres or create a new one |
| `/api/centres/<id>` | GET | Get a single centre |
| `/api/bookings` | POST | Book spaces at a centre (reduces `spaces_available`) |
| `/api/bookings/<id>` | GET | Get a booking by ID |

**Models:**

- **SupportRequest** – `description`, `category`, `area`, `priority`, `status`, timestamps (`created_at`, `updated_at`). Statuses: `new`, `in progress`, `completed`.
- **CoolingCentre** – `name`, `area`, `capacity`, `spaces_available`, `opening_hours`, `status` (open/closed).
- **Booking** – Links a request to a centre with date, time, and spaces required.

### Django Dashboard (`dashboard/`)

The dashboard view fetches live data from the Flask API on every page load:

1. **Request metrics** – Total requests, outstanding count (new + in progress), completed count, in-progress count displayed as metric cards.
2. **Support request table** – Full breakdown of each request with ID, description, category, area, priority, and status badges.
3. **Cooling centre availability table** – Name, area, status, opening hours, capacity vs available spaces, and a visual utilisation bar (green/yellow/red). A summary row shows totals across all centres.

All figures reflect the latest data saved to the Flask API database.

### Automated Launch Script (`start.sh`)

The `./start.sh` script starts both services with one command:

- Activates the virtual environment automatically
- Starts Flask on port 5000 (or 5001 if occupied)
- Applies Django migrations
- Starts Django dashboard on port 8000
- Handles Ctrl+C to cleanly shut down both servers

## Getting Started

### Prerequisites

- Python 3.12+
- `curl` (used by the launch script for health checks)

### Quick Start – One Command

```bash
./start.sh
```

This starts **both** the Flask API and Django dashboard. Open:

- Dashboard: http://127.0.0.1:8000/
- API docs (try in browser): http://127.0.0.1:5000/api/health

### Manual Setup

If you prefer to start services individually:

#### 1. Install dependencies

```bash
python -m pip install flask flask-sqlalchemy pytest django requests cryptography
```

Or use the project's virtual environment (recommended):

```bash
python -m venv .env
source .env/bin/activate
pip install -r requirements.txt
```

#### 2. Start Flask API

```bash
# Default port 5000:
python app.py

# Custom port:
PORT=5001 python app.py
```

Flask serves on `http://127.0.0.1:<port>` with debug mode enabled. The database (`heatshield.db`) is created automatically on first run.

#### 3. Start Django Dashboard

Set the API URL and start the server:

```bash
# Default (Flask on port 5000):
DJANGO_FLASK_API_URL=http://127.0.0.1:5000/api python manage.py migrate --noinput
DJANGO_FLASK_API_URL=http://127.0.0.1:5000/api python manage.py runserver 8000

# If Flask is on port 5001:
DJANGO_FLASK_API_URL=http://127.0.0.1:5001/api python manage.py migrate --noinput
DJANGO_FLASK_API_URL=http://127.0.0.1:5001/api python manage.py runserver 8000
```

The `DJANGO_FLASK_API_URL` environment variable tells Django where to fetch data from the Flask API. Default is `http://127.0.0.1:5000/api`.

## Testing

### Run all tests

```bash
python -m pytest tests/ dashboard/tests.py -v
```

### Test suites

| File | Coverage |
|---|---|
| `tests/test_bookings.py` | Flask API – CRUD, validation, filtering, error handling (82 assertions) |
| `dashboard/tests.py` | Django dashboard – metric counts, centre utilisation, empty data, API failure handling (7 tests) |
| `tests/test_us19.py` | Security testing – input sanitisation, generic errors, encryption at rest, security event logging (22 tests) |

Tests use an in-memory SQLite database for the Flask side and mocked HTTP responses for the Django side.

## Project Structure

```
├── app.py                  # Flask API – models, routes, CRUD endpoints, security (US19)
├── manage.py               # Django CLI utility
├── start.sh                # Launch script (Flask + Django)
├── requirements.txt        # pip dependencies
├── db.sqlite3              # Django database (ignored in git)
│                           # security_events.log – US19 security audit log (not committed)
│
├── dashboard/              # Django app
│   ├── __init__.py
│   ├── urls.py             # App-level URL routing → views.index
│   ├── tests.py            # Dashboard metric & availability tests
│   └── views.py            # index() view – fetches from Flask API, computes metrics
│
├── dashboard_project/      # Django project config
│   ├── settings.py         # INSTALLED_APPS, templates dir, DB config
│   ├── urls.py             # Root URL routing (includes dashboard app)
│   └── wsgi.py             # WSGI entry point
│
├── templates/dashboard/    # HTML template
│   └── index.html          # Staff dashboard UI – metric cards + tables
│
└── tests/                  # Flask API tests
    └── test_bookings.py    # Full CRUD, validation, filtering, error handling
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `PORT` (Flask) | `5000` | Port for the Flask API server |
| `DJANGO_FLASK_API_URL` | `http://127.0.0.1:5000/api` | Base URL Django uses to fetch data from Flask |
| `FLASK_DEBUG` | `false` | Enable debug mode (disables generic error handling when true) |
| `HEATSHIELD_ENCRYPTION_KEY` | *(none)* | Fernet encryption key for encrypting sensitive fields at rest. When set, request descriptions are encrypted before storage and decrypted on read. Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

## Notes

- **Authentication** – US06 provides Bearer-token authentication and role-based access control for protected Flask API write operations. The Django dashboard itself does not yet enforce user authentication. Dashboard access controls must be implemented before deployment.
- **Data persistence** – Both services use SQLite databases (`heatshield.db` for Flask, `db.sqlite3` for Django). These are ignored in `.gitignore`.
- **Port fallback** – If port 5000 is occupied by another application, `start.sh` automatically starts Flask on port 5001 and updates the Django API URL accordingly.
- **Security (US19)** – All user inputs are HTML-sanitised to prevent XSS attacks. Error messages are generic and never expose system internals or stack traces. Sensitive data can be encrypted at rest via `HEATSHIELD_ENCRYPTION_KEY`. Failed auth attempts, access denials, and rejected inputs are logged to `security_events.log` for audit purposes.


## US06 – Staff Authentication and Access Control

US06 introduces Bearer-token authentication, role-based
authorisation and audit logging for protected API operations.

### Protected Endpoints

The following operations require an authorised staff account:

- PATCH `/api/requests/<id>`
- DELETE `/api/requests/<id>`
- POST `/api/centres`
- POST `/api/bookings`

Supported roles are `staff` and `supervisor`.

Requests without valid authentication return HTTP 401.
Authenticated users without sufficient permissions receive HTTP 403.

### Authentication Header

Protected API requests must include:

`Authorization: Bearer <staff_access_token>`

Staff tokens are generated using the internal `provision_staff()`
function. Only token hashes are stored in the database.

Access tokens must remain confidential and must never be
committed to GitHub.

Public support-request submission remains available through
POST `/api/requests`.

### Audit Logging

Successful protected operations record the responsible staff
member, action, affected resource and timestamp.

For implementation details, testing evidence and limitations,
see `US06_SECURITY_DOCUMENTATION.md`.


## US19 – Security Testing

The API is hardened against common web threats:

- **Input sanitisation** — All user strings are HTML-escaped before storage; SQL injection prevented by parameterised queries and enum validation.
- **Generic error messages** — Global handlers return plain JSON errors. No stack traces or system internals leak to clients (debug mode off by default).
- **Encryption at rest** — Request descriptions encrypted with Fernet when `HEATSHIELD_ENCRYPTION_KEY` is set; falls back to plain text in dev.
- **Security event logging** — Failed auth, access denied, and rejected inputs are logged to `security_events.log`.

22 new tests cover all four ACs (`python -m pytest tests/test_us19.py`).