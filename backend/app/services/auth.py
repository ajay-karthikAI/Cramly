from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import re


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
HASH_ITERATIONS = 210_000


class AuthError(Exception):
    pass


def normalize_email(email: str) -> str:
    value = email.strip().lower()
    if not EMAIL_RE.match(value):
        raise AuthError("Enter a valid email address.")
    return value


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), HASH_ITERATIONS)
    return f"pbkdf2_sha256${HASH_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected = password_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations))
    return hmac.compare_digest(digest.hex(), expected)


def create_access_token(user_id: str, secret: str, minutes: int) -> str:
    now = datetime.now(timezone.utc)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    signing_input = f"{_b64_json(header)}.{_b64_json(payload)}"
    signature = _b64_bytes(hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest())
    return f"{signing_input}.{signature}"


def verify_access_token(token: str, secret: str) -> str:
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("Invalid session token.")
    signing_input = f"{parts[0]}.{parts[1]}"
    expected = _b64_bytes(hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, parts[2]):
        raise AuthError("Invalid session token.")

    try:
        payload = json.loads(urlsafe_b64decode(_pad(parts[1])).decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthError("Invalid session token.") from exc

    if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
        raise AuthError("Session expired.")
    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise AuthError("Invalid session token.")
    return user_id


def _b64_json(value: dict) -> str:
    return _b64_bytes(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _b64_bytes(value: bytes) -> str:
    return urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _pad(value: str) -> bytes:
    return (value + "=" * (-len(value) % 4)).encode("utf-8")
