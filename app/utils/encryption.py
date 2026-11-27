"""Encryption-at-rest helpers (US19 AC3)."""

import os

# US19 AC3: Encryption at rest for sensitive data.
_ENCRYPTION_KEY = os.environ.get("HEATSHIELD_ENCRYPTION_KEY", None)

if _ENCRYPTION_KEY is not None:
    from cryptography.fernet import Fernet

    _fernet = Fernet(_ENCRYPTION_KEY.encode())

    def encrypt_field(plaintext):
        """Encrypt a string field before storing in the database."""
        if plaintext is None:
            return None
        return _fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt_field(ciphertext):
        """Decrypt an encrypted field after reading from the database."""
        if ciphertext is None:
            return None
        try:
            return _fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except Exception:
            # Decryption failed — return raw value to avoid leaking errors.
            return "[encrypted]"

else:
    # No encryption key configured; store data as-is (development mode).
    def encrypt_field(plaintext):
        """No-op when no encryption key is set."""
        return plaintext

    def decrypt_field(ciphertext):
        """No-op when no encryption key is set."""
        return ciphertext
