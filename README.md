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

### Test Database

Tests use a separate in-memory SQLite database.
The test database is recreated for each test,
preventing changes to the development database.

### Testing Framework

pytest and Flask's built-in test client.
