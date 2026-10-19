from __future__ import annotations

from cryptography.fernet import Fernet


def encrypt(fernet: Fernet, plain: str) -> str:
    return fernet.encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt(fernet: Fernet, secret: str) -> str:
    return fernet.decrypt(secret.encode("ascii")).decode("utf-8")
