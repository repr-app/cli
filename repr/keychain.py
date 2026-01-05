"""
Secure credential storage using OS keychain.

Supports:
- macOS: Keychain
- Windows: Credential Manager
- Linux: Secret Service (libsecret)

Falls back to encrypted file storage if keychain is unavailable.
"""

import base64
import hashlib
import json
import os
import secrets
import tempfile
from pathlib import Path
from typing import Any

# Service name for keychain entries
SERVICE_NAME = "repr-cli"

# Fallback storage location
REPR_HOME = Path(os.getenv("REPR_HOME", Path.home() / ".repr"))
SECRETS_FILE = REPR_HOME / ".secrets.enc"
KEY_FILE = REPR_HOME / ".secrets.key"

# Try to import keyring
_keyring_available = False
try:
    import keyring
    from keyring.errors import KeyringError, PasswordDeleteError
    _keyring_available = True
except ImportError:
    keyring = None
    KeyringError = Exception
    PasswordDeleteError = Exception


def is_keyring_available() -> bool:
    """Check if OS keychain is available and functional."""
    if not _keyring_available:
        return False
    
    try:
        # Test keychain access with a dummy operation
        test_key = f"repr_keychain_test_{secrets.token_hex(4)}"
        keyring.set_password(SERVICE_NAME, test_key, "test")
        result = keyring.get_password(SERVICE_NAME, test_key)
        keyring.delete_password(SERVICE_NAME, test_key)
        return result == "test"
    except Exception:
        return False


def _get_encryption_key() -> bytes:
    """Get or generate encryption key for fallback storage."""
    REPR_HOME.mkdir(parents=True, exist_ok=True)
    
    if KEY_FILE.exists():
        return base64.b64decode(KEY_FILE.read_text().strip())
    
    # Generate new key
    key = secrets.token_bytes(32)
    KEY_FILE.write_text(base64.b64encode(key).decode())
    KEY_FILE.chmod(0o600)  # Owner read/write only
    return key


def _simple_encrypt(data: str, key: bytes) -> str:
    """Simple XOR encryption with key derivation.
    
    Note: This is NOT cryptographically secure for serious use.
    It's a fallback when keychain is unavailable.
    For production, consider using cryptography library.
    """
    # Derive a longer key using hash
    derived = hashlib.sha256(key).digest()
    data_bytes = data.encode('utf-8')
    
    # XOR with repeating key
    encrypted = bytes(
        b ^ derived[i % len(derived)]
        for i, b in enumerate(data_bytes)
    )
    return base64.b64encode(encrypted).decode()


def _simple_decrypt(encrypted: str, key: bytes) -> str:
    """Decrypt data encrypted with _simple_encrypt."""
    derived = hashlib.sha256(key).digest()
    encrypted_bytes = base64.b64decode(encrypted)
    
    decrypted = bytes(
        b ^ derived[i % len(derived)]
        for i, b in enumerate(encrypted_bytes)
    )
    return decrypted.decode('utf-8')


def _load_fallback_secrets() -> dict[str, str]:
    """Load secrets from fallback encrypted file."""
    if not SECRETS_FILE.exists():
        return {}
    
    try:
        key = _get_encryption_key()
        encrypted = SECRETS_FILE.read_text().strip()
        decrypted = _simple_decrypt(encrypted, key)
        return json.loads(decrypted)
    except Exception:
        return {}


def _save_fallback_secrets(secrets_dict: dict[str, str]) -> None:
    """Save secrets to fallback encrypted file."""
    REPR_HOME.mkdir(parents=True, exist_ok=True)
    key = _get_encryption_key()
    encrypted = _simple_encrypt(json.dumps(secrets_dict), key)
    
    # Atomic write
    fd, tmp_path = tempfile.mkstemp(dir=REPR_HOME, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(encrypted)
        os.replace(tmp_path, SECRETS_FILE)
        SECRETS_FILE.chmod(0o600)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def store_secret(key: str, value: str) -> bool:
    """
    Store a secret in the OS keychain or fallback storage.
    
    Args:
        key: Unique identifier for the secret (e.g., 'auth_token', 'byok_openai')
        value: Secret value to store
    
    Returns:
        True if stored successfully
    """
    if _keyring_available:
        try:
            keyring.set_password(SERVICE_NAME, key, value)
            return True
        except KeyringError:
            pass
    
    # Fallback to encrypted file
    secrets_dict = _load_fallback_secrets()
    secrets_dict[key] = value
    _save_fallback_secrets(secrets_dict)
    return True


def get_secret(key: str) -> str | None:
    """
    Retrieve a secret from the OS keychain or fallback storage.
    
    Args:
        key: Unique identifier for the secret
    
    Returns:
        Secret value or None if not found
    """
    if _keyring_available:
        try:
            value = keyring.get_password(SERVICE_NAME, key)
            if value is not None:
                return value
        except KeyringError:
            pass
    
    # Fallback to encrypted file
    secrets_dict = _load_fallback_secrets()
    return secrets_dict.get(key)


def delete_secret(key: str) -> bool:
    """
    Delete a secret from the OS keychain or fallback storage.
    
    Args:
        key: Unique identifier for the secret
    
    Returns:
        True if deleted, False if not found
    """
    deleted = False
    
    if _keyring_available:
        try:
            keyring.delete_password(SERVICE_NAME, key)
            deleted = True
        except (KeyringError, PasswordDeleteError):
            pass
    
    # Also remove from fallback if present
    secrets_dict = _load_fallback_secrets()
    if key in secrets_dict:
        del secrets_dict[key]
        _save_fallback_secrets(secrets_dict)
        deleted = True
    
    return deleted


def list_secrets() -> list[str]:
    """
    List all secret keys (not values).
    
    Note: OS keychain doesn't support listing, so this only works for fallback storage.
    
    Returns:
        List of secret keys
    """
    secrets_dict = _load_fallback_secrets()
    return list(secrets_dict.keys())


def migrate_plaintext_token(plaintext_token: str, key: str = "auth_token") -> bool:
    """
    Migrate a plaintext token to secure storage.
    
    Args:
        plaintext_token: The token to migrate
        key: Key to store under (default: 'auth_token')
    
    Returns:
        True if migration successful
    """
    return store_secret(key, plaintext_token)


def get_storage_info() -> dict[str, Any]:
    """
    Get information about current storage backend.
    
    Returns:
        Dict with storage type and details
    """
    using_keyring = _keyring_available and is_keyring_available()
    
    return {
        "backend": "keyring" if using_keyring else "encrypted_file",
        "keyring_available": _keyring_available,
        "keyring_functional": is_keyring_available() if _keyring_available else False,
        "fallback_file": str(SECRETS_FILE) if SECRETS_FILE.exists() else None,
        "service_name": SERVICE_NAME,
    }

