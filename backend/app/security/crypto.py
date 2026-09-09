"""Шифрування MCP-токенів перед записом у Supabase.

Вимога хакатону: токен гостя Сільпо ніколи не залишає бекенд.
У БД лежить лише ciphertext; ключ — в env (TOKEN_ENCRYPTION_KEY).
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


def _fernet() -> Fernet:
    key = get_settings().token_encryption_key
    if not key:
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY не заданий. Згенеруй: "
            "python -c \"from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())\""
        )
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        # Дозволяємо довільний рядок як парольну фразу — деривуємо валідний Fernet-ключ.
        derived = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
        return Fernet(derived)


def encrypt(value: str | None) -> str | None:
    if value is None:
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:  # ключ змінили / дані пошкоджені
        raise RuntimeError("Не вдалось розшифрувати токен: ключ TOKEN_ENCRYPTION_KEY змінився?") from exc
