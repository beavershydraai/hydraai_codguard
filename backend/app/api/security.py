"""Security schemes declared in the contract, and the dependencies that verify shop app tokens
and the call controller's Google ID tokens."""

import os
from typing import Annotated

import google.auth.exceptions
from fastapi import Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.api.errors import ApiError
from app.auth import AuthError, User, verify_token
from app.schemas.enums import ErrorCode

bearer_auth = HTTPBearer(
    scheme_name="bearerAuth",
    bearerFormat="JWT",
    description="Access token of a shop user from `POST /api/v1/auth/login` "
    "(role owner or staff). Firebase ID tokens will replace it (E7.1).",
    auto_error=False,
)

intake_api_key = APIKeyHeader(
    name="X-Api-Key",
    scheme_name="intakeApiKey",
    description="Per-shop API key for external sales tools.",
    auto_error=False,
)

controller_id_token = HTTPBearer(
    scheme_name="googleIdToken",
    bearerFormat="JWT",
    description="Google-signed ID token of the call controller's service account "
    "(codguard-runtime), with the backend URL as audience. See docs/call-controller.md.",
    auto_error=False,
)


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_auth)],
) -> User:
    """The signed-in shop user. Routes that read or change shop data must depend on this;
    the router-level `bearer_auth` only declares the scheme in the contract."""
    if credentials is None:
        raise ApiError(401, ErrorCode.UNAUTHORIZED, "Unauthorized", "Missing access token.")
    try:
        return verify_token(credentials.credentials)
    except AuthError as exc:
        raise ApiError(401, ErrorCode.UNAUTHORIZED, "Unauthorized", str(exc)) from exc


CurrentUser = Annotated[User, Security(current_user)]


def controller_identity(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(controller_id_token)],
) -> str:
    """The call controller's service account (docs/call-controller.md, "Internal API").

    The token must be a Google-signed ID token with INTERNAL_AUDIENCE as audience, for a verified
    email listed in CONTROLLER_SERVICE_ACCOUNTS (comma-separated). INTERNAL_AUTH=off skips the
    check on a developer's machine; it is ignored on Cloud Run (K_SERVICE is set)."""
    if os.environ.get("INTERNAL_AUTH") == "off" and not os.environ.get("K_SERVICE"):
        return "local"
    unauthorized = ApiError(
        401,
        ErrorCode.UNAUTHORIZED,
        "Unauthorized",
        "Missing or invalid Google ID token, or not a controller service account.",
    )
    audience = os.environ.get("INTERNAL_AUDIENCE")
    if credentials is None or not audience:
        raise unauthorized
    try:
        claims = id_token.verify_oauth2_token(
            credentials.credentials, google_requests.Request(), audience=audience
        )
    except (ValueError, google.auth.exceptions.GoogleAuthError):
        raise unauthorized from None
    allowed = {
        email.strip()
        for email in os.environ.get("CONTROLLER_SERVICE_ACCOUNTS", "").split(",")
        if email.strip()
    }
    if not claims.get("email_verified") or claims.get("email") not in allowed:
        raise unauthorized
    return claims["email"]
