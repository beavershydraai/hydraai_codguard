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
| `app/agents/` | ADK function-node workflows (E4.7), runners, decision log and contact claims; contact channels return `mock: true` |
| `config/cod_guard_rules_apac.yaml` | Rule set: the policy engine reads `tier_policy`; the ADK routing and log read `baseline_alignment.api_actions` and `metadata.rule_set_version`. Tests also inspect `enums.outcomes`. The image copies this folder; `tests/test_rules_file.py` checks consistency |
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

## ADK orchestration (E4.7)

`app/agents/agent.py` defines two ADK 2.x `Workflow` graphs with Python function nodes:

- `on_new_order`: `load_order → score → decide → act`. A new intake order runs this graph before
  the API responds, without a manual trigger. The deterministic engine in `app/decision` chooses
  the action; `decide` logs it and routes to ship, confirmation link, AI call, deposit or review.
- `on_contact_event`: `load_event → post_interaction → act`. `run_contact_event` accepts buyer
  responses, call outcomes and no-response events through the lifecycle functions. Confirmation
  and timer decisions use the existing score; buyer edits retain the lifecycle's rescoring rules.
  This runner is not yet wired to an HTTP endpoint or a scheduled timer.

These graphs implement orchestration. They contain no Gemini agents for signal extraction,
message composition or voice, and no LLM chooses the score, tier or action. Contact branches
reserve a send and return `mock: true`; the E5 channel integration still needs to perform the contact
and deliver its result to `run_contact_event`. The graphs do not wait for a buyer to respond.

The intake route stays synchronous: FastAPI runs it in a worker thread, where `run_new_order_sync`
uses `asyncio.run` to create a loop for that run. ADK executes synchronous nodes on that loop, and
the nodes make blocking Firestore calls. Changing the route to `async def` would put those calls
on the shared request loop.

Scoring retries transient errors for at most three attempts. Exhausted retries and invalid events
use the runner's review fallback; an unsupported action routes to review. A previously decided
order is not scored or contacted again. Firestore `decision_log` records the action, rule and
policy versions independently of the in-memory ADK session. `probs` remains empty until the
seven-outcome model is available; the current binary model supplies `failure_probability`.

Claims are created before each mock send. Confirmation links and deposit requests use
`order_id:action`; AI calls use `order_id:ai_call:1` and `order_id:ai_call:2`, each tied to its decision.
The call branch records `attempts.ai_call` on the order, so a due no-response event can claim the
second attempt and the next event can move to review. A replay cannot claim another call for the
same decision.

`tests/test_pipeline.py` runs the real ADK graphs with a fake store, decision log and risk model.
It covers ship, confirmation, retry and review paths, duplicate sends, decision-log fields,
contact events and the second call followed by review. `tests/test_intake.py` checks the automatic
intake trigger and returned decision status. These tests verify orchestration with mock contacts;
they do not establish live-channel completion, Gemini Live compatibility or Cloud Run cold-start
performance.

## ADK dependency constraints

`pyproject.toml` allows `google-adk>=2.11,<3`; `uv.lock` currently resolves `2.11.0`. This admits later
2.x releases when the lock is updated and excludes 3.x. Locked installs keep the tested resolution.

ADK 2.11.0 requires `websockets>=15.0.1,<16` and `opentelemetry-api>=1.39,<=1.42.1`.
The resolved `google-genai` 2.30.1 also requires `tenacity<9.2.0`. These upstream constraints remain
even with the wider ADK version range. The compatible locked set includes `websockets` 15.0.1,
`opentelemetry-api` 1.42.1, `tenacity` 9.1.4, `fastapi` 0.141.1 and `google-api-core` 2.34.0;
changing the ADK requirement alone does not restore the newer versions displaced during resolution.

The E5 Gemini Live client must be tested with this locked set, including `websockets` 15.x, before
claiming compatibility. See `../docs/gemini-live.md` for the Live API configuration requirements.
