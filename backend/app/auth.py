"""Shop app sign-in: one admin account from the environment and signed bearer tokens.

A stand-in for Firebase Auth (E7.1). The account and the signing key come from the environment
(Secret Manager in the cloud), never from code:

- ADMIN_USERNAME, ADMIN_PASSWORD: the only account that can sign in.
- AUTH_TOKEN_SECRET: HMAC key for the tokens. Rotating it signs everyone out.
- ADMIN_SHOP_ID: shop the account belongs to (default `shop_demo`, the intake demo shop).
- ADMIN_EMAIL: email shown for the account (default `admin@codguard.local`).

Sign-in is disabled unless the three required variables are set.
"""

import hmac
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.schemas.enums import Role

TOKEN_TTL = timedelta(hours=12)
_ALGORITHM = "HS256"
_ISSUER = "codguard"


class AuthError(Exception):
    """Sign-in failed or a token is not valid. The message is safe to show to the client."""


@dataclass(frozen=True)
class User:
    user_id: str
    username: str
    email: str
    display_name: str
    role: Role
    shop_id: str


@dataclass(frozen=True)
class _Config:
    username: str
    password: str
    secret: str
    shop_id: str
    email: str


def _config() -> _Config:
    username = os.environ.get("ADMIN_USERNAME", "")
    password = os.environ.get("ADMIN_PASSWORD", "")
    secret = os.environ.get("AUTH_TOKEN_SECRET", "")
    if not (username and password and secret):
        raise AuthError("Sign-in is not configured on this server.")
    return _Config(
        username=username,
        password=password,
        secret=secret,
        shop_id=os.environ.get("ADMIN_SHOP_ID", "shop_demo"),
        email=os.environ.get("ADMIN_EMAIL", "admin@codguard.local"),
    )


def _admin(config: _Config) -> User:
    return User(
        user_id=f"usr_{config.username}",
        username=config.username,
        email=config.email,
        display_name="Admin",
        role=Role.OWNER,
        shop_id=config.shop_id,
    )


def authenticate(username: str, password: str) -> User:
    config = _config()
    # Compare both fields in constant time, and always both, so timing reveals neither.
    username_ok = hmac.compare_digest(username.encode(), config.username.encode())
    password_ok = hmac.compare_digest(password.encode(), config.password.encode())
    if not (username_ok and password_ok):
        raise AuthError("Wrong username or password.")
    return _admin(config)


def issue_token(user: User, now: datetime | None = None) -> tuple[str, datetime]:
    config = _config()
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + TOKEN_TTL
    claims = {
        "iss": _ISSUER,
        "sub": user.user_id,
        "username": user.username,
        "role": user.role.value,
        "shop_id": user.shop_id,
        "iat": issued_at,
        "exp": expires_at,
    }
    return jwt.encode(claims, config.secret, algorithm=_ALGORITHM), expires_at


def verify_token(token: str) -> User:
    config = _config()
    try:
        claims = jwt.decode(
            token,
            config.secret,
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("The access token has expired. Sign in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("The access token is not valid.") from exc
    # Only the configured account can hold a token; a renamed account invalidates old tokens.
    if claims.get("username") != config.username:
        raise AuthError("The access token is not valid.")
    return _admin(config)
