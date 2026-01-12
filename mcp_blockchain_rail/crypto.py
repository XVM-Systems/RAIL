"""Encryption utilities for API keys and private keys."""

import base64
import getpass
import hashlib
import os

from cryptography.fernet import Fernet


def generate_salt() -> bytes:
    """Generate random salt for key derivation.

    Returns:
        16-byte random salt.
    """
    return os.urandom(16)


def derive_key(password: str, salt: bytes) -> bytes:
    """Derive encryption key from password using PBKDF2.

    Args:
        password: User-provided password.
        salt: Random salt for key derivation.

    Returns:
        32-byte encryption key.
    """
    kdf = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt,
        100000,  # iterations
        dklen=32,
    )
    return base64.urlsafe_b64encode(kdf)


def encrypt_data(data: str, key: bytes) -> bytes:
    """Encrypt data with Fernet.

    Args:
        data: Data to encrypt.
        key: Encryption key (32 bytes).

    Returns:
        Encrypted data as bytes.
    """
    f = Fernet(key)
    return f.encrypt(data.encode())


def decrypt_data(encrypted: bytes, key: bytes) -> str:
    """Decrypt data with Fernet.

    Args:
        encrypted: Encrypted data.
        key: Encryption key (32 bytes).

    Returns:
        Decrypted data as string.

    Raises:
        Exception: If decryption fails.
    """
    f = Fernet(key)
    return f.decrypt(encrypted).decode()


def encrypt_to_base64(data: str, key: bytes) -> str:
    """Encrypt data and return base64-encoded string.

    Args:
        data: Data to encrypt.
        key: Encryption key.

    Returns:
        Base64-encoded encrypted string.
    """
    encrypted = encrypt_data(data, key)
    return base64.b64encode(encrypted).decode()


def decrypt_from_base64(encrypted_b64: str, key: bytes) -> str:
    """Decrypt base64-encoded encrypted string.

    Args:
        encrypted_b64: Base64-encoded encrypted data.
        key: Encryption key.

    Returns:
        Decrypted data as string.
    """
    encrypted = base64.b64decode(encrypted_b64.encode())
    return decrypt_data(encrypted, key)


class EncryptionManager:
    """Manager for encryption/decryption operations."""

    def __init__(self, password: str, salt: bytes | None = None):
        """Initialize encryption manager.

        Args:
            password: Encryption password.
            salt: Optional salt (generates new one if not provided).
        """
        self.salt = salt or generate_salt()
        self.key = derive_key(password, self.salt)

    def encrypt(self, data: str) -> str:
        """Encrypt data and return base64 string.

        Args:
            data: Data to encrypt.

        Returns:
            Base64-encoded encrypted string.
        """
        return encrypt_to_base64(data, self.key)

    def decrypt(self, encrypted_b64: str) -> str:
        """Decrypt base64-encoded string.

        Args:
            encrypted_b64: Base64-encoded encrypted data.

        Returns:
            Decrypted data as string.
        """
        return decrypt_from_base64(encrypted_b64, self.key)

    def get_salt_base64(self) -> str:
        """Get salt as base64 string.

        Returns:
            Base64-encoded salt.
        """
        return base64.b64encode(self.salt).decode()

    def get_password(self) -> str:
        """Prompt for password interactively.

        Returns:
            User-entered password.
        """
        return getpass.getpass("Enter encryption password: ")

    @staticmethod
    def from_password(
        password: str, salt: bytes | None = None
    ) -> "EncryptionManager":
        """Create EncryptionManager from password.

        Args:
            password: Encryption password.
            salt: Optional salt.

        Returns:
            EncryptionManager instance.
        """
        return EncryptionManager(password, salt)
