# COM6402-Group2 – Heat Shield

## Unit and API Testing (US03b)

Automated tests are implemented using pytest to verify
the reliability of the Heat Shield Flask API.

### Requirements
- Python 3
- Flask
- Flask-SQLAlchemy
- pytest

### Install Dependencies

Run the following command in the project terminal:

python -m pip install flask flask-sqlalchemy pytest

### Run the Tests

From the project root directory, execute:

python -m pytest tests/ -v

### Tests Covered

1. Support request model conversion
2. Creating and retrieving support requests
3. Updating support requests
4. Rejecting missing required fields
5. Handling requests that do not exist
6. Filtering requests by area
7. Rejecting invalid JSON input
8. Deleting support requests
9. Checking the health endpoint
10. Rejecting whitespace-only descriptions
11. Rejecting requests without an area

### Test Database

Tests use a separate in-memory SQLite database.
The test database is recreated for each test,
preventing changes to the development database.

### Testing Framework

pytest and Flask's built-in test client.


## US06 – Staff Authentication

Protected API operations require an authorised staff account.

The following endpoints require an HTTP Bearer token:

- PATCH /api/requests/<id>
- DELETE /api/requests/<id>
- POST /api/centres
- POST /api/bookings

The supported roles are `staff` and `supervisor`.

Requests without valid authentication return HTTP 401.
Authenticated users without sufficient permissions receive HTTP 403.

### Authentication Header

Include the following header when calling protected endpoints:

Authorization: Bearer <staff_access_token>

Staff tokens are generated using the internal
`provision_staff()` function. Only token hashes are
stored in the database.

Tokens must be kept confidential and must not be
committed to GitHub.

Public support-request submission remains available
through POST /api/requests.

For implementation details, testing evidence and
limitations, see `US06_SECURITY_DOCUMENTATION.md`.