"""Security schemes declared in the contract. Verification is not implemented yet."""

from fastapi.security import APIKeyHeader, HTTPBearer

firebase_auth = HTTPBearer(
    scheme_name="firebaseAuth",
    bearerFormat="JWT",
    description="Firebase ID token of a shop user (role in custom claims: owner or staff).",
    auto_error=False,
)

intake_api_key = APIKeyHeader(
    name="X-Api-Key",
    scheme_name="intakeApiKey",
    description="Per-shop API key for external sales tools.",
    auto_error=False,
)
