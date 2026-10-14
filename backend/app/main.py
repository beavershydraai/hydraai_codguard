"""COD Guard API application."""

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute

from app.api.errors import PROBLEM_JSON, install_error_handlers, problem_responses
from app.api.v1 import router as v1_router

API_VERSION = "0.1.0"

TAGS = [
    {"name": "auth", "description": "Sign-in for the shop app."},
    {"name": "me", "description": "Signed-in user."},
    {"name": "shop", "description": "Shop settings and tier policy."},
    {"name": "orders", "description": "Order inbox, order page, edits, overrides, manual calls."},
    {"name": "calls", "description": "AI confirmation calls."},
    {"name": "delivery", "description": "Delivery outcomes that update phone history."},
    {"name": "dashboard", "description": "ROI dashboard and backtest."},
    {"name": "intake", "description": "Order intake for external sales tools (API key)."},
    {
        "name": "public",
        "description": "Buyer confirmation page. No login; the link token is the credential.",
    },
    {"name": "demo", "description": "Demo controls for the hackathon. Not for production."},
]

DESCRIPTION = """
Contract between the COD Guard backend and its clients (shop web app, buyer confirmation page,
external sales tools).

Conventions:

- Money is integer VND in fields ending `_vnd`.
- Times are ISO 8601 with offset; shops operate in Vietnam time (`+07:00`).
- Enum values are English snake_case. Each enum's description lists its English UI labels.
- Errors use `application/problem+json` (RFC 9457) with a machine-readable `code`.
- Lists use cursor pagination: pass `next_cursor` back as `cursor`.
"""


def _operation_id(route: APIRoute) -> str:
    return route.name


def _use_problem_json(schema: dict[str, Any]) -> None:
    """Error bodies are problem+json. FastAPI's default 422 (HTTPValidationError) is replaced
    by the ProblemDetail response used everywhere else."""
    validation = problem_responses(422)[422]
    for path in schema.get("paths", {}).values():
        for op in path.values():
            for code, resp in op.get("responses", {}).items():
                content = resp.get("content", {})
                if code == "422" and "HTTPValidationError" in str(content):
                    resp["description"] = validation["description"]
                    content = {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ProblemDetail"},
                            **validation["content"]["application/json"],
                        }
                    }
                if code[0] in "45" and "application/json" in content:
                    resp["content"] = {PROBLEM_JSON: content["application/json"]}
    components = schema.get("components", {}).get("schemas", {})
    if "HTTPValidationError" not in str(schema.get("paths")):
        components.pop("HTTPValidationError", None)
        components.pop("ValidationError", None)


def create_app() -> FastAPI:
    app = FastAPI(
        title="COD Guard API",
        version=API_VERSION,
        description=DESCRIPTION.strip(),
        openapi_tags=TAGS,
        generate_unique_id_function=_operation_id,
    )
    install_error_handlers(app)
    app.include_router(v1_router)

    # Not /healthz: Cloud Run reserves some paths ending in "z" and answers them itself.
    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            tags=app.openapi_tags,
        )
        _use_problem_json(schema)
        schema["servers"] = [{"url": "http://localhost:8080", "description": "Local"}]
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
    return app


app = create_app()
