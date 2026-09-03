import os

from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    key = (os.getenv("ENCRYPTION_KEY") or "").strip().encode()
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    return Fernet(key)


def encrypt_credentials(plaintext) -> str:
    return _fernet().encrypt(str(plaintext).encode()).decode()


def decrypt_credentials(ciphertext) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise ValueError(
            "Could not decrypt credentials: invalid key or corrupted value"
        )
