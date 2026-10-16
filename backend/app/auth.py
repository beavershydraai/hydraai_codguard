"""Shop app sign-in: an admin account and shop accounts from the environment, and signed
bearer tokens.

A stand-in for Firebase Auth (E7.1). The accounts and the signing key come from the environment
(Secret Manager in the cloud), never from code:

- ADMIN_USERNAME, ADMIN_PASSWORD: the admin account (the demo shop). The username may be an email.
- SHOP_ACCOUNTS: more owner accounts, each with its own shop, as a JSON list of
  {"username", "password_hash", "shop_id", "name"}; `password_hash` is from `hash_password`
  (PBKDF2-SHA256), never the password. Optional.
- AUTH_TOKEN_SECRET: HMAC key for the tokens. Rotating it signs everyone out.
- ADMIN_SHOP_ID: shop the account belongs to (default `shop_demo`, the intake demo shop).
- ADMIN_EMAIL: email shown for the account (default: the username when it is an email,
  otherwise `admin@codguard.local`).

Sign-in is disabled unless the three required variables are set.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
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
        email=os.environ.get("ADMIN_EMAIL")
        or (username if "@" in username else "admin@codguard.local"),
    )


def _admin(config: _Config) -> User:
    return User(
        user_id="usr_admin",
        username=config.username,
        email=config.email,
        display_name="Admin",
        role=Role.OWNER,
        shop_id=config.shop_id,
    )


_ITERATIONS = 200_000


def hash_password(password: str, salt: bytes | None = None) -> str:
    """`pbkdf2_sha256$<iterations>$<salt>$<hash>` for a SHOP_ACCOUNTS entry."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    encode = base64.b64encode
    return f"pbkdf2_sha256${_ITERATIONS}${encode(salt).decode()}${encode(digest).decode()}"


def _password_ok(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt, digest = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), base64.b64decode(salt), int(iterations)
        )
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


def _accounts() -> list[dict]:
    """SHOP_ACCOUNTS, or no shop account when it is unset."""
    raw = os.environ.get("SHOP_ACCOUNTS", "").strip()
    return json.loads(raw) if raw else []


def _owner(account: dict) -> User:
    return User(
        user_id=f"usr_{account['shop_id']}",
        username=account["username"],
        email=account["username"],
        display_name=account.get("name") or "Owner",
        role=Role.OWNER,
        shop_id=account["shop_id"],
    )


def _user(username: str) -> User | None:
    """The account with this username, as a user; None when there is none."""
    config = _config()
    if hmac.compare_digest(username.encode(), config.username.encode()):
        return _admin(config)
    for account in _accounts():
        if hmac.compare_digest(username.encode(), account["username"].encode()):
            return _owner(account)
    return None


def authenticate(username: str, password: str) -> User:
    config = _config()
    # Compare both fields in constant time, and always both, so timing reveals neither.
    username_ok = hmac.compare_digest(username.encode(), config.username.encode())
    password_ok = hmac.compare_digest(password.encode(), config.password.encode())
    if username_ok and password_ok:
        return _admin(config)
    for account in _accounts():
        if hmac.compare_digest(username.encode(), account["username"].encode()):
            if _password_ok(password, account["password_hash"]):
                return _owner(account)
            break
    raise AuthError("Wrong username or password.")


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
    # Only a configured account can hold a token; a renamed account invalidates old tokens.
    user = _user(str(claims.get("username", "")))
    if user is None:
        raise AuthError("The access token is not valid.")
    return user
