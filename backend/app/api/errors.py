"""Problem-details errors and the shared error responses used in the contract."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.common import FieldError, ProblemDetail
from app.schemas.enums import ErrorCode

PROBLEM_JSON = "application/problem+json"

_TITLES = {
    400: ("Bad request", ErrorCode.VALIDATION_ERROR),
    401: ("Unauthorized", ErrorCode.UNAUTHORIZED),
    403: ("Forbidden", ErrorCode.FORBIDDEN),
    404: ("Not found", ErrorCode.NOT_FOUND),
    409: ("Conflict", ErrorCode.CONFLICT),
    410: ("Gone", ErrorCode.LINK_EXPIRED),
    422: ("Validation error", ErrorCode.VALIDATION_ERROR),
    429: ("Too many requests", ErrorCode.RATE_LIMITED),
}

_DESCRIPTIONS = {
    400: "Malformed request or file.",
    401: "Missing or invalid credentials.",
    403: "Authenticated but not allowed (e.g. staff changing policy).",
    404: "Resource not found.",
    409: "Request conflicts with the current state. See `code`.",
    410: "Confirmation link expired or already used.",
    422: "Request body or parameters failed validation. See `errors`.",
    429: "Rate limit hit (demo paths).",
}


_EXAMPLES: dict[int, dict] = {
    400: {"detail": "CSV header is missing the buyer_phone column."},
    401: {"detail": "Missing or expired access token."},
    403: {"detail": "Only the shop owner can change the policy."},
    404: {"detail": "Order ord_99 not found."},
    409: {"detail": "An order with external_id FB-20261009-0042 already exists."},
    410: {"detail": "This confirmation link expired 48 hours after it was sent."},
    422: {
        "errors": [
            {
                "loc": ["body", "buyer_phone"],
                "msg": "String should match pattern '^\\+?[0-9]{9,15}$'",
                "type": "string_pattern_mismatch",
            }
        ]
    },
    429: {"detail": "Demo rate limit reached. Try again in a minute."},
}


def problem_example(status: int, code: ErrorCode | None = None, **fields: object) -> dict:
    title, default_code = _TITLES[status]
    example = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "code": (code or default_code).value,
    }
    example.update(_EXAMPLES.get(status, {}))
    example.update(fields)
    return example


def problem_responses(
    *codes: int, examples: dict[int, dict] | None = None
) -> dict[int | str, dict]:
    """Error responses for a route, documented with the ProblemDetail schema and an example."""
    examples = examples or {}
    return {
        code: {
            "model": ProblemDetail,
            "description": _DESCRIPTIONS[code],
            "content": {"application/json": {"example": examples.get(code, problem_example(code))}},
        }
        for code in codes
    }


class ApiError(Exception):
    def __init__(
        self, status: int, code: ErrorCode, title: str, detail: str | None = None, **extra: object
    ) -> None:
        self.problem = ProblemDetail(status=status, code=code, title=title, detail=detail, **extra)


class NotImplementedYet(ApiError):
    """Raised by contract stubs until the endpoint is implemented."""

    def __init__(self, operation: str) -> None:
        super().__init__(
            501,
            ErrorCode.NOT_IMPLEMENTED,
            "Not implemented",
            f"`{operation}` is defined in the contract but not implemented yet.",
        )


def _problem(problem: ProblemDetail) -> JSONResponse:
    return JSONResponse(
        problem.model_dump(mode="json", exclude_none=True),
        status_code=problem.status,
        media_type=PROBLEM_JSON,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _problem(exc.problem)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            FieldError(loc=list(e["loc"]), msg=e["msg"], type=e["type"]) for e in exc.errors()
        ]
        return _problem(
            ProblemDetail(
                status=422, code=ErrorCode.VALIDATION_ERROR, title="Validation error", errors=errors
            )
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        title, code = _TITLES.get(exc.status_code, ("Error", ErrorCode.CONFLICT))
        return _problem(
            ProblemDetail(status=exc.status_code, code=code, title=title, detail=str(exc.detail))
        )
