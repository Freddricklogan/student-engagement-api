"""Password hashing and JWT issue/verify.

Replaces the legacy scheme entirely: no shared static key, no query-string
credential, no ``==`` comparison of secrets.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.domain.entities import Role
from app.domain.errors import AuthenticationError
from app.infrastructure.settings import Settings

#: bcrypt work factor. 12 is the usual production floor; it is deliberately slow.
BCRYPT_ROUNDS = 12

#: bcrypt silently truncates beyond 72 bytes, so reject rather than truncate.
_MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    """Hash a password with bcrypt.

    ``bcrypt`` is used directly rather than through passlib: passlib 1.7 imports
    the stdlib ``crypt`` module, which is deprecated in 3.12 and removed in 3.13.
    """
    encoded = password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        msg = f"Password must be at most {_MAX_PASSWORD_BYTES} bytes."
        raise ValueError(msg)
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time password verification.

    Returns ``False`` rather than raising on a malformed stored hash, so a bad
    row cannot turn a login attempt into a 500.
    """
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:_MAX_PASSWORD_BYTES], hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(
    *, subject: str, role: Role, settings: Settings, expires_delta: timedelta | None = None
) -> tuple[str, int]:
    """Return ``(token, expires_in_seconds)`` for an OAuth2 bearer token."""
    delta = expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    now = datetime.now(UTC)
    expire = now + delta
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role.value,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, int(delta.total_seconds())


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    """Verify signature, expiry, issuer and audience. Raise on any failure."""
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Access token is invalid.") from exc

    if not claims.get("sub") or claims.get("role") not in {r.value for r in Role}:
        raise AuthenticationError("Access token is missing required claims.")
    return claims
