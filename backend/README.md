# COD Guard backend

FastAPI service. For now it holds the API contract: every endpoint is defined with its request
and response schemas and returns `501 not_implemented` until it is built.

```bash
uv sync                                            # installs Python 3.12 and dependencies
uv run uvicorn app.main:app --reload --port 8080   # http://localhost:8080/docs
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run python -m app.openapi_export                # regenerate ../api/openapi.yaml
```

| Path | Contents |
|---|---|
| `app/main.py` | App factory, OpenAPI settings |
| `app/api/v1/` | Routes: `shop_app.py` (shop web app), `external.py` (intake, buyer page, demo) |
| `app/api/errors.py` | Problem-details errors and the shared error responses |
| `app/schemas/` | Request and response models with examples |
| `tests/` | Contract and app tests |

See `../api/README.md` for how the frontend uses the contract.
