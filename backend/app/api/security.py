"""Security schemes declared in the contract, and the dependency that verifies shop app tokens."""

from typing import Annotated

from fastapi import Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

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
