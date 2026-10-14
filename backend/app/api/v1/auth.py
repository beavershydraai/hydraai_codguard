"""Shop app sign-in."""

from fastapi import APIRouter

from app.api.errors import ApiError, problem_example, problem_responses
from app.auth import AuthError, authenticate, issue_token
from app.schemas.auth import LoginRequest, LoginResponse
from app.schemas.enums import ErrorCode
from app.schemas.shops import Me

auth_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_router.post(
    "/login",
    response_model=LoginResponse,
    responses=problem_responses(
        401,
        422,
        examples={
            401: problem_example(401, detail="Wrong username or password."),
            422: problem_example(
                422,
                errors=[
                    {
                        "loc": ["body", "password"],
                        "msg": "String should have at least 1 character",
                        "type": "string_too_short",
                    }
                ],
            ),
        },
    ),
    summary="Sign in to the shop app",
    description="Exchanges a username and password for a bearer access token valid for 12 hours. "
    "A stand-in for Firebase Auth (E7.1): the only account is the admin account configured on "
    "the server.",
)
def login(body: LoginRequest) -> LoginResponse:
    try:
        user = authenticate(body.username, body.password)
        token, expires_at = issue_token(user)
    except AuthError as exc:
        raise ApiError(401, ErrorCode.UNAUTHORIZED, "Unauthorized", str(exc)) from exc
    return LoginResponse(
        access_token=token,
        expires_at=expires_at,
        user=Me(
            user_id=user.user_id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            shop_id=user.shop_id,
        ),
    )
