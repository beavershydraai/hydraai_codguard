# COD Guard backend

FastAPI service with an API contract, order intake, scoring and lifecycle services. Endpoints that
are not yet wired to their services return `501 not_implemented`.

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
| `app/decision/` | Order lifecycle (E4.1): nine statuses, transactional edits and rescoring, buyer/call/delivery outcomes, confirmed-order guard, order-detail view. Policy engine (E4.2): action per tier, expected-loss gate and escalation |
| `config/cod_guard_rules_apac.yaml` | Rule set. Only the `tier_policy` section is read by the code today; the image copies this folder. `tests/test_rules_file.py` keeps the rest in line with AGENTS.md, `ShopSettings` and the engines |
| `tests/` | Contract and app tests |
| `Dockerfile` | Production image: uv-built virtualenv, non-root user, listens on `$PORT` |

See `../api/README.md` for how the frontend uses the contract.

## Order lifecycle services (E4.1)

`app/decision/lifecycle.py` applies all order transitions through `OrderStore.transact`, so the state
read, scoring history, current decision and timeline change together. Intake uses `score_order`;
`edit_order` checks the shop and editable state, then rescores only when a field changes. Buyer and call
results use `apply_buyer_response` and `apply_call_outcome`. Timers use `on_no_response`; shipping and
carrier results use `mark_shipped` and `apply_delivery`.

Confirmation is stored once. A later edit still records a fresh score, but cannot schedule another
contact for a confirmed order. `app/decision/views.py` exposes the current score and prior runs through
`order_detail(doc)` without changing the stored document.

An invalid-phone hard rule can still hold a confirmed order for review; it schedules no contact.
Staff decisions retain their status during rescoring. In the demo, increasing `prepaid_vnd` on an
engine-decided order awaiting a deposit releases it after rescoring, unless the phone is invalid.

Shop order-detail and edit routes stay at `501 not_implemented` until Firebase token verification can
provide a trusted shop identity. The lifecycle functions are available for integration by those routes;
buyer-page tokens, call sessions, contact limits and timer scheduling belong to their own epics.
