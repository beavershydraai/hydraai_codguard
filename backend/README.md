# COD Guard backend

FastAPI service. For now it holds the API contract: every endpoint is defined with its request
and response schemas and returns `501 not_implemented` until it is built.
E3's reusable AI scoring modules are implemented; the E2 scoring flow will connect them to orders.

```bash
uv sync                                            # installs Python 3.12 and dependencies
uv run uvicorn app.main:app --reload --port 8080   # http://localhost:8080/docs
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run python -m app.openapi_export                # regenerate ../api/openapi.yaml
uv run python -m scoring.ai.eval --offline --output ../docs/evaluations/e3-offline.json
```

Container image (same as CI and Cloud Run):

```bash
docker build -t codguard-backend .
docker run -p 8080:8080 codguard-backend            # http://localhost:8080/health
```

Every push to `main` publishes the image to `ghcr.io/beavershydraai/hydraai_codguard/backend`
with tags `sha-<commit>` and `main`.

| Path | Contents |
|---|---|
| `app/main.py` | App factory, OpenAPI settings |
| `app/api/v1/` | Routes: `shop_app.py` (shop web app), `external.py` (intake, buyer page, demo) |
| `app/api/errors.py` | Problem-details errors and the shared error responses |
| `app/schemas/` | Request and response models with examples |
| `scoring/ai/` | E3 Gemini gateway, address/chat extraction, reason checks and evaluation |
| `scoring/ai/service.py` | E2 integration boundary; never sets scores or decisions |
| `tests/` | Contract and app tests |
| `Dockerfile` | Production image: uv-built virtualenv, non-root user, listens on `$PORT` |

See `../api/README.md` for how the frontend uses the contract.
See [`../docs/e3-ai.md`](../docs/e3-ai.md) for E3 integration and configuration.
