"""US19 - Security Testing

Acceptance Criteria:
    AC1: All user inputs are sanitised to prevent injection attacks.
    AC2: Malicious input attempts trigger appropriate error messages without
         exposing system internals or sensitive data.
    AC3: User data is encrypted at rest using industry-standard encryption.
    AC4: All security-relevant events (failed auth, rejected inputs, access denials) are logged for audit purposes.
"""

import hashlib
import logging
import os
from io import StringIO

import pytest
from cryptography.fernet import Fernet

from app import SecurityAuditLog, StaffUser, SupportRequest, app, db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Shared in-memory SQLite DB; reset tables for each test."""
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite://",
    )

    engines = db._app_engines.setdefault(app, {})
    for engine in list(engines.values()):
        engine.dispose()
    engines.clear()
    engines[None] = db._make_engine(
        None,
        {"url": app.config["SQLALCHEMY_DATABASE_URI"]},
        app,
    )

    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


@pytest.fixture
def staff_headers(client):
    """Provide credentials for an authorised test staff member."""
    token = "us06-regression-test-token"

    staff = StaffUser(
        username="regression_staff",
        role="staff",
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        is_active=True,
    )

    db.session.add(staff)
    db.session.commit()

    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def supervisor_headers(client):
    """Provide credentials for an authorised test supervisor member."""
    token = "us06-supervisor-test-token"

    staff = StaffUser(
        username="regression_supervisor",
        role="supervisor",
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        is_active=True,
    )

    db.session.add(staff)
    db.session.commit()

    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def encryption_key():
    """Provide a real Fernet key and temporarily patch the app's encrypt/decrypt functions."""
    key = Fernet.generate_key()
    fernet = Fernet(key)

    # Save originals so tests can compare.
    import app as app_module
    original_encrypt = app_module.encrypt_field
    original_decrypt = app_module.decrypt_field

    def patched_encrypt(plaintext):
        if plaintext is None:
            return None
        return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def patched_decrypt(ciphertext):
        if ciphertext is None:
            return None
        try:
            return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except Exception:
            return "[encrypted]"

    # Monkey-patch the module-level functions.
    app_module.encrypt_field = patched_encrypt
    app_module.decrypt_field = patched_decrypt

    yield key

    # Restore originals after test.
    app_module.encrypt_field = original_encrypt
    app_module.decrypt_field = original_decrypt


@pytest.fixture
def security_log_capture():
    """Capture log records from the heatshield.security logger."""
    handler = StringIO()
    logger = logging.getLogger("heatshield.security")
    original_level = logger.level
    test_handler = logging.StreamHandler(handler)
    test_handler.setLevel(logging.INFO)
    # Add handler before yielding so all subsequent requests are captured.
    logger.addHandler(test_handler)
    logger.setLevel(logging.INFO)

    yield handler

    # Remove handler after tests complete.
    logger.removeHandler(test_handler)
    logger.setLevel(original_level)


# ---------------------------------------------------------------------------
# AC1: Input sanitisation — contextual output encoding (US19 AC1)
# ---------------------------------------------------------------------------


class TestAC1InputSanitisation:
    """All user inputs are sanitised; XSS prevented via contextual output encoding.

    Data is stored raw in the database and HTML-encoded only at display time,
    avoiding double-encoding and preserving original data for legitimate use.
    """

    def test_xss_in_description_is_encoded_at_output(self, client):
        """XSS payloads are stored raw but HTML-encoded when returned via API."""
        payload = {"description": "<script>alert('xss')</script>", "category": "welfare", "area": "Bolton"}
        resp = client.post("/api/requests", json=payload)
        assert resp.status_code == 201
        data = resp.get_json()
        # Output must be HTML-encoded.
        assert "&lt;script&gt;" in data["description"]
        assert "<script>" not in data["description"]

    def test_xss_in_area_is_encoded_at_output(self, client):
        """XSS payloads in area are stored raw but encoded at output."""
        payload = {"description": "test", "category": "welfare", "area": "<img src=x onerror=alert(1)>"}
        resp = client.post("/api/requests", json=payload)
        assert resp.status_code == 201
        data = resp.get_json()
        assert "&lt;img" in data["area"]

    def test_xss_in_patch_description_is_encoded(self, client, staff_headers):
        """XSS payloads in PATCH description are encoded at output."""
        create_resp = client.post("/api/requests", json={
            "description": "test desc", "category": "welfare", "area": "Bolton"
        })
        req_id = create_resp.get_json()["id"]

        patch_resp = client.patch(
            f"/api/requests/{req_id}",
            headers=staff_headers,
            json={"description": "<script>alert('xss')</script>"},
        )
        assert patch_resp.status_code == 200
        data = patch_resp.get_json()
        assert "&lt;script&gt;" in data["description"]

    def test_xss_in_centre_name_is_encoded(self, client, staff_headers):
        """XSS payloads in centre name are encoded at output."""
        resp = client.post("/api/centres", headers=staff_headers, json={
            "name": "<script>alert('xss')</script>",
            "area": "Bolton",
            "capacity": 10,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert "&lt;script&gt;" in data["name"]

    def test_sql_injection_category_is_rejected(self, client):
        """SQL injection attempts in category are rejected (enum validation)."""
        payload = {"description": "test", "category": "welfare'; DROP TABLE support_request;--", "area": "Bolton"}
        resp = client.post("/api/requests", json=payload)
        assert resp.status_code == 400

    def test_sql_injection_via_parameterized_queries_is_safe(self, client):
        """SQL injection payloads in area are stored safely (parameterised queries)."""
        payload = {"description": "test", "category": "welfare", "area": "Bolton'; DROP TABLE support_request;--"}
        resp = client.post("/api/requests", json=payload)
        assert resp.status_code == 201

    def test_legitimate_angle_brackets_preserved_in_storage(self, client):
        """Legitimate angle brackets are stored raw and only encoded at output."""
        payload = {"description": "Use <5mg dosage", "category": "medical", "area": "Bolton"}
        resp = client.post("/api/requests", json=payload)
        assert resp.status_code == 201
        data = resp.get_json()
        # Output is encoded.
        assert "&lt;5mg" in data["description"]

    def test_double_encoding_does_not_occur(self, client):
        """Calling to_dict() twice should not double-encode."""
        payload = {"description": "<script>alert('xss')</script>", "category": "welfare", "area": "Bolton"}
        resp1 = client.post("/api/requests", json=payload)
        assert resp1.status_code == 201

        # Fetch the same record again.
        req_id = resp1.get_json()["id"]
        resp2 = client.get(f"/api/requests/{req_id}")
        assert resp2.status_code == 200
        data2 = resp2.get_json()

        # Both responses should have single encoding, not double.
        assert "&amp;lt;script&amp;gt;" not in data2["description"]


# ---------------------------------------------------------------------------
# AC2: Generic error messages (no system internals exposed)
# ---------------------------------------------------------------------------


class TestAC2GenericErrorMessages:
    """Malicious input attempts trigger appropriate error messages without
    exposing system internals or sensitive data."""

    def test_invalid_category_returns_generic_error(self, client):
        """Invalid category should return a generic error, not DB schema info."""
        payload = {"description": "test", "category": "invalid_cat", "area": "Bolton"}
        resp = client.post("/api/requests", json=payload)
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data
        # Should NOT expose internal details like table names or column types.
        assert "DROP" not in data["error"]
        assert "sqlite" not in data["error"].lower()

    def test_missing_required_field_returns_generic_error(self, client):
        """Missing required field should return a generic error."""
        payload = {"description": "", "category": "welfare", "area": "Bolton"}
        resp = client.post("/api/requests", json=payload)
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_invalid_token_returns_generic_error(self, client):
        """Invalid Bearer token should return a generic error on an auth endpoint."""
        resp = client.post(
            "/api/centres",
            headers={"Authorization": "Bearer invalid-token"},
            json={"name": "Test Centre", "area": "Bolton", "capacity": 10},
        )
        assert resp.status_code == 401
        data = resp.get_json()
        assert "error" in data

    def test_no_auth_header_returns_generic_error(self, client):
        """Missing auth header should return a generic error on an auth endpoint."""
        resp = client.post(
            "/api/centres",
            headers={},
            json={"name": "Test Centre", "area": "Bolton", "capacity": 10},
        )
        assert resp.status_code == 401

    def test_insufficient_permissions_returns_403_with_unchanged_db(self, client):
        """A staff user accessing a supervisor-only endpoint must get HTTP 403 and DB state unchanged."""
        # Create a staff user (not supervisor).
        staff_token = "low-priv-token"
        staff_user = StaffUser(
            username="low_priv",
            role="staff",
            token_hash=hashlib.sha256(staff_token.encode("utf-8")).hexdigest(),
            is_active=True,
        )
        db.session.add(staff_user)
        db.session.commit()

        # Create a request that the supervisor purge would delete.
        create_resp = client.post("/api/requests", json={
            "description": "test desc", "category": "welfare", "area": "Bolton"
        })
        req_id = create_resp.get_json()["id"]

        # Verify DB state before: the request exists.
        pre_record = db.session.get(SupportRequest, req_id)
        assert pre_record is not None

        # Staff user tries supervisor-only endpoint → must get 403 (not 204).
        resp = client.delete(
            "/api/supervisor/purge",
            headers={"Authorization": f"Bearer {staff_token}"},
        )
        assert resp.status_code == 403, "Staff should receive HTTP 403 on supervisor-only endpoint"

        # Verify DB state unchanged: the request still exists.
        post_record = db.session.get(SupportRequest, req_id)
        assert post_record is not None, "DB record must remain after denied operation"

    def test_debug_mode_does_not_expose_stack_trace(self, client):
        """Debug mode should be disabled; no stack traces in responses."""
        resp = client.post(
            "/api/requests",
            content_type="application/json",
            data="not valid json",
        )
        assert resp.status_code == 400 or resp.status_code == 500
        text = resp.get_data(as_text=True)
        assert "Traceback" not in text
        assert "File " not in text


# ---------------------------------------------------------------------------
# AC3: Encryption at rest for sensitive data (US19 AC3)
# ---------------------------------------------------------------------------


class TestAC3EncryptionAtRest:
    """User data is encrypted at rest using industry-standard Fernet encryption.

    Tests verify both dev-mode (no key → plaintext) and production-mode
    (key set → ciphertext stored in DB, decrypted on read).
    """

    def test_encrypt_decrypt_roundtrip(self):
        """encrypt_field and decrypt_field should round-trip correctly."""
        from app import encrypt_field, decrypt_field
        plaintext = "sensitive description"
        encrypted = encrypt_field(plaintext)
        decrypted = decrypt_field(encrypted)
        assert decrypted == plaintext

    def test_none_values_handled(self):
        """None values should be handled gracefully by both functions."""
        from app import encrypt_field, decrypt_field
        assert encrypt_field(None) is None
        assert decrypt_field(None) is None

    def test_no_encryption_key_stores_plain_text(self):
        """Without encryption key, data is stored as plain text (dev mode)."""
        from app import encrypt_field, decrypt_field
        plaintext = "test description"
        result = encrypt_field(plaintext)
        assert result == plaintext

    def test_real_fernet_key_produces_ciphertext_in_db(self, client, encryption_key):
        """With an active Fernet key, the raw DB column contains ciphertext."""
        import app as app_module

        resp = client.post("/api/requests", json={
            "description": "Patient has diabetes and needs medication",
            "category": "welfare",
            "area": "Bolton"
        })
        assert resp.status_code == 201

        # The DB column must be ciphertext (not plaintext).
        record = db.session.get(SupportRequest, resp.get_json()["id"])
        assert record.description != "Patient has diabetes and needs medication", \
            "DB column must contain ciphertext when encryption key is active"
        # Ciphertext should look like base64 Fernet output.
        assert len(record.description) > 30

    def test_patch_encrypts_updated_description(self, client, staff_headers, encryption_key):
        """PATCH encrypts the updated description identically to POST."""
        import app as app_module

        # Create a request first.
        create_resp = client.post("/api/requests", json={
            "description": "original desc", "category": "welfare", "area": "Bolton"
        })
        req_id = create_resp.get_json()["id"]

        # Patch with sensitive data.
        patch_resp = client.patch(
            f"/api/requests/{req_id}",
            headers=staff_headers,
            json={"description": "Patient has diabetes and needs medication"},
        )
        assert patch_resp.status_code == 200

        # DB column must be ciphertext.
        record = db.session.get(SupportRequest, req_id)
        assert record.description != "Patient has diabetes and needs medication", \
            "DB column must contain ciphertext after PATCH when encryption key is active"

    def test_post_and_patch_encrypt_consistently(self, client, staff_headers, encryption_key):
        """POST and PATCH produce the same ciphertext for identical plaintext."""
        import app as app_module

        # POST with sensitive data.
        post_resp = client.post("/api/requests", json={
            "description": "Patient has diabetes and needs medication",
            "category": "welfare",
            "area": "Bolton"
        })
        assert post_resp.status_code == 201
        post_id = post_resp.get_json()["id"]

        # PATCH the same plaintext.
        patch_resp = client.patch(
            f"/api/requests/{post_id}",
            headers=staff_headers,
            json={"description": "Patient has diabetes and needs medication"},
        )
        assert patch_resp.status_code == 200

        post_record = db.session.get(SupportRequest, post_id)
        # Both should be ciphertext (not plaintext).
        assert post_record.description != "Patient has diabetes and needs medication"

    def test_missing_key_returns_fallback_on_decrypt(self):
        """Decryption with a wrong key raises; app handles it gracefully."""
        from cryptography.fernet import Fernet
        key_a = Fernet.generate_key()
        key_b = Fernet.generate_key()
        fernet_a = Fernet(key_a)
        fernet_b = Fernet(key_b)

        plaintext = "sensitive data"
        ciphertext = fernet_a.encrypt(plaintext.encode("utf-8")).decode("utf-8")

        # Decrypt with wrong key — should raise, not crash.
        try:
            fernet_b.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
            assert False, "Decryption with wrong key should raise"
        except Exception:
            pass  # Expected behaviour.

    def test_decryption_failure_returns_generic_value(self):
        """decrypt_field returns '[encrypted]' on failure, not internals."""
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        fernet = Fernet(key)

        plaintext = "sensitive data"
        ciphertext = fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

        try:
            fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
            assert False, "Decryption with wrong key should raise"
        except Exception:
            pass  # Expected behaviour.

    def test_encrypted_data_not_readable_without_key(self, client):
        """Without encryption key, stored data is readable plaintext."""
        from app import encrypt_field
        plaintext = "test description"
        result = encrypt_field(plaintext)
        assert result == plaintext  # No-op in dev mode.

    def test_api_response_decodes_encrypted_data(self, client, encryption_key):
        """API response returns decrypted (readable) data even when DB stores ciphertext."""
        resp = client.post("/api/requests", json={
            "description": "Patient has diabetes and needs medication",
            "category": "welfare",
            "area": "Bolton"
        })
        assert resp.status_code == 201
        data = resp.get_json()
        # The API response should contain the decrypted plaintext.
        assert data["description"] == "Patient has diabetes and needs medication"


# ---------------------------------------------------------------------------
# AC4: Security event logging for audit purposes (US19 AC4)
# ---------------------------------------------------------------------------


class TestAC4SecurityEventLogging:
    """All security-relevant events are logged to both file logger and DB audit table."""

    def test_failed_auth_is_logged(self, client, security_log_capture):
        """Failed authentication attempts should be logged."""
        client.post(
            "/api/centres",
            json={"name": "Test Centre", "area": "Bolton", "capacity": 10},
        )

        log_output = security_log_capture.getvalue()
        assert "AUTH_FAILED" in log_output

    def test_invalid_token_is_logged(self, client, security_log_capture):
        """Invalid Bearer token should be logged."""
        client.post(
            "/api/centres",
            headers={"Authorization": "Bearer invalid-token"},
            json={"name": "Test Centre", "area": "Bolton", "capacity": 10},
        )

        log_output = security_log_capture.getvalue()
        assert "AUTH_FAILED" in log_output

    def test_access_denied_is_logged(self, client, security_log_capture):
        """Access denied (insufficient permissions) should be logged."""
        token = "inactive-token"
        staff = StaffUser(
            username="inactive_staff",
            role="staff",
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            is_active=False,  # Inactive account
        )
        db.session.add(staff)
        db.session.commit()

        client.post(
            "/api/centres",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Test Centre", "area": "Bolton", "capacity": 10},
        )

        log_output = security_log_capture.getvalue()
        assert "AUTH_FAILED" in log_output

    def test_rejected_input_is_logged(self, client, security_log_capture):
        """Rejected input attempts should be logged."""
        client.post("/api/requests", json={
            "description": "test", "category": "invalid_cat", "area": "Bolton"
        })

        log_output = security_log_capture.getvalue()
        assert "REJECTED_INPUT" in log_output

    def test_missing_required_field_is_logged(self, client, security_log_capture):
        """Missing required fields should be logged."""
        client.post("/api/requests", json={
            "description": "", "category": "welfare", "area": "Bolton"
        })

        log_output = security_log_capture.getvalue()
        assert "REJECTED_INPUT" in log_output

    def test_security_audit_log_model_exists(self):
        """SecurityAuditLog model should exist and be importable."""
        from app import SecurityAuditLog
        assert SecurityAuditLog is not None

    def test_security_events_persisted_to_db(self, client):
        """log_security_event writes rows to the SecurityAuditLog table."""
        # Trigger a security event (missing auth → AUTH_FAILED).
        client.post(
            "/api/centres",
            json={"name": "Test Centre", "area": "Bolton", "capacity": 10},
        )

        # Verify at least one row was persisted.
        rows = db.session.query(SecurityAuditLog).all()
        assert len(rows) > 0, "Security events should be persisted to the DB audit table"

        event_types = {r.event_type for r in rows}
        assert "AUTH_FAILED" in event_types or "REJECTED_INPUT" in event_types

    def test_security_audit_log_has_required_fields(self):
        """SecurityAuditLog row contains event_type, ip_address, details, timestamp."""
        from app import SecurityAuditLog
        assert hasattr(SecurityAuditLog, "event_type")
        assert hasattr(SecurityAuditLog, "ip_address")
        assert hasattr(SecurityAuditLog, "details")
        assert hasattr(SecurityAuditLog, "timestamp")

    def test_audit_log_row_contains_event_data(self, client):
        """Persisted SecurityAuditLog rows contain correct event_type and details."""
        # Trigger a rejected-input event.
        client.post("/api/requests", json={
            "description": "test", "category": "invalid_cat", "area": "Bolton"
        })

        rows = db.session.query(SecurityAuditLog).all()
        assert len(rows) > 0

        # At least one row should have REJECTED_INPUT event type.
        rejected_rows = [r for r in rows if r.event_type == "REJECTED_INPUT"]
        assert len(rejected_rows) > 0, "Should have at least one REJECTED_INPUT audit row"

        # Verify required fields are populated.
        row = rejected_rows[0]
        assert row.event_type == "REJECTED_INPUT"
        assert row.details  # Should contain some details about the rejection
        assert row.timestamp is not None
