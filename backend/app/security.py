"""Password hashing and JWT issuing/decoding.

Hashing uses stdlib PBKDF2-HMAC-SHA256 so the sample runs with no native
dependencies. For the production plant, swap ``hash_password``/``verify_password``
for argon2 or bcrypt - nothing else needs to change.
"""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings

_ALGORITHM = "HS256"
_PBKDF2_ROUNDS = 260_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    expected = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
    return hmac.compare_digest(expected.hex(), digest_hex)


def create_access_token(subject: str, role: str, user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "uid": user_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
