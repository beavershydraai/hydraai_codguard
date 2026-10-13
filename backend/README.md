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
| `app/data/` | Order record (`docs/data-model.md`): phone normalisation and hashing, the Firestore document, the training label and snapshot row |
| `app/risk/` | Scoring engine (features, Model 1, hard rules, tier, action) and the jobs `jobs/train.py`, `jobs/monitor.py` (`tasks/E2.3-risk-features.md`) |
| `app/decision/` | Policy engine (E4.2): action per tier, no contact when the expected loss does not cover its cost, escalation when the buyer does not respond |
| `config/cod_guard_rules_apac.yaml` | Rule set. Only the `tier_policy` section is read by the code today; the image copies this folder. `tests/test_rules_file.py` keeps the rest in line with AGENTS.md, `ShopSettings` and the engines |
| `tests/` | Contract and app tests |
| `Dockerfile` | Production image: uv-built virtualenv, non-root user, listens on `$PORT` |

See `../api/README.md` for how the frontend uses the contract.
