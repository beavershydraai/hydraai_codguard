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
| `app/api/v1/auth.py` | `POST /auth/login` for the shop app |
| `app/api/security.py` | Security schemes and `CurrentUser`, the dependency that verifies the bearer token |
| `app/auth.py` | Admin account from the environment, token signing and verification |
| `app/api/errors.py` | Problem-details errors and the shared error responses |
| `app/schemas/` | Request and response models with examples |
| `app/data/` | Order record (`docs/data-model.md`): phone normalisation and hashing, the Firestore document, the training label and snapshot row |
| `app/risk/` | Scoring engine (features, Model 1, exact TreeSHAP on the pre-calibration probability, hard rules, tier, action) and the jobs `jobs/train.py`, `jobs/monitor.py` (`tasks/E2.3-risk-features.md`). The training job also stores `latest/backtest.json` (`backtest.py`, E9.1), served by `GET /api/v1/dashboard/backtest` |
| `app/demo/` | The demo shop's synthetic world (`world.py`: branches in VN, SG and PH, buyers, behaviour, outcomes), the 90-day history seed (`seed.py`) and the live simulator (`simulate.py`, Cloud Run job `codguard-simulate`); orders sent with a `noagents` test key skip the Gemini assessment |
| `app/data/branches.py` | Branches and countries from `config/branches.yaml`: currency, local time, phone code and costs |
| `app/decision/inbox.py` | Order inbox for `GET /orders`: status/tier filters, search, sort and cursor paging over one shop's orders |
| `app/decision/` | Order lifecycle (E4.1): nine statuses, transactional edits and rescoring, buyer/call/delivery outcomes, confirmed-order guard, order-detail view. Policy engine (E4.2): action per tier, expected-loss gate and escalation |
| `app/agents/` | ADK workflows (E4.7), two advisory assessment agents, runners, decision log and contact claims; contact channels return `mock: true`, except AI calls once calls are configured |
| `app/calls/` | AI calls on the backend side (E5): contact rules, the `CallJob` with amounts and dates in words, publishing to Pub/Sub `call-jobs`, the controller's status and result, and applying the outcome to the orders ([docs/call-controller.md](../docs/call-controller.md)) |
| `app/telephony/` | Call controller for the Asterisk VM: ARI client, RTP for External Media, the Gemini Live agent, the controller service `python -m app.telephony.controller` (Pub/Sub, claim, result outbox), and `python -m app.telephony.dial` ([docs/call-controller.md](../docs/call-controller.md)) |
| `config/cod_guard_rules_apac.yaml` | Rule set: the policy engine reads `tier_policy`; the ADK routing and log read `baseline_alignment.api_actions` and `metadata.rule_set_version`. Tests also inspect `enums.outcomes`. The image copies this folder; `tests/test_rules_file.py` checks consistency |
| `tests/` | Contract and app tests |
| `Dockerfile` | Production image: uv-built virtualenv, non-root user, listens on `$PORT` |

See `../api/README.md` for how the frontend uses the contract.

## Order inbox and order page (E7.2, E7.3)

`GET /api/v1/orders` and `GET /api/v1/orders/{order_id}` read the signed-in user's shop only;
another shop's order answers 404. The inbox runs one Firestore query per request (`shop_id`, and
`placed_at` when `placed_from`/`placed_to` are given), then filters by status and tier, searches and
sorts in `app/decision/inbox.py`: the tier sits inside `scoring` and the COD amount is derived,
so Firestore cannot do it. That suits demo-sized shops (a few thousand orders each).

- Search `q` ignores case and Vietnamese diacritics on the buyer name, order id and external id,
  and matches phones written as `09…`, `+84 9…` or any three or more consecutive digits.
- `next_cursor` is an offset tied to the filters and sort it came from; reusing it with other
  filters answers 422.
- The query needs the composite index (`shop_id`, `placed_at` descending) from
  `infra/firestore.indexes.json`. Create it once per database, for example:

  ```bash
  gcloud firestore indexes composite create --project=ai-codguard --database=vn-synthetic \
    --collection-group=orders \
    --field-config=field-path=shop_id,order=ascending \
    --field-config=field-path=placed_at,order=descending
  ```

Running it locally needs Firestore credentials: `gcloud auth application-default login`.

## Sign-in (stand-in for Firebase Auth, E7.1)

`POST /api/v1/auth/login` takes `{"username", "password"}` and returns a bearer token (HS256 JWT,
valid 12 hours) plus the user. There is one account, read from the environment:

| Variable | Use |
|---|---|
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | The account (`admin@gmail.com` / `admin12345` in `.env.example`, local only) |
| `AUTH_TOKEN_SECRET` | HMAC key for the tokens; changing it signs everyone out |
| `ADMIN_SHOP_ID`, `ADMIN_EMAIL` | Optional: the account's shop (default `shop_demo`) and email (default: the username if it is an email) |

Sign-in is disabled until the first three are set. A route that reads or changes shop data takes a
`user: CurrentUser` parameter, which answers 401 for a missing, invalid or expired token and
gives the route the user's `shop_id` and role. `GET /api/v1/me` is the first such route. The
router-level `bearer_auth` dependency only declares the scheme in the contract; it checks nothing.

```bash
ADMIN_USERNAME=admin@gmail.com ADMIN_PASSWORD=admin12345 AUTH_TOKEN_SECRET=dev \
  uv run uvicorn app.main:app --reload --port 8080
curl -s -X POST localhost:8080/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"username": "admin@gmail.com", "password": "admin12345"}'
```

## Order lifecycle services (E4.1)

`app/decision/lifecycle.py` applies order transitions through `OrderStore.transact`, so committed
scoring history, current decision and timeline change together. Intake uses `prepare_score`
to compute an uncommitted snapshot, then `commit_prepared_score` to verify the stored order has not
changed and save its deterministic decision after assessment. `score_order` remains available to
other callers. `edit_order` checks the shop and editable state, then rescores only when a field
changes. Buyer and call results use `apply_buyer_response` and `apply_call_outcome`.
Timers use `on_no_response`; shipping and carrier results use `mark_shipped` and `apply_delivery`.

Confirmation is stored once. A later edit still records a fresh score, but cannot schedule another
contact for a confirmed order. `app/decision/views.py` exposes the current score and prior runs through
`order_detail(doc)` without changing the stored document.

An invalid-phone hard rule can still hold a confirmed order for review; it schedules no contact.
Staff decisions retain their status during rescoring. In the demo, increasing `prepaid_vnd` on an
engine-decided order awaiting a deposit releases it after rescoring, unless the phone is invalid.

Shop order-detail and edit routes stay at `501 not_implemented` until they are wired to the lifecycle;
the trusted shop identity now comes from `CurrentUser` (see "Sign-in"). The lifecycle functions are available for integration by those routes;
buyer-page tokens, call sessions, contact limits and timer scheduling belong to their own epics.

## ADK orchestration (E4.7)

`app/agents/agent.py` defines two ADK 2.x `Workflow` graphs with Python function nodes:

- `on_new_order`: `load_order → score → assess_order → decide → act`. A new intake order runs this
  graph before the API responds, without a manual trigger. Scoring does not persist a decision.
  After advisory assessment, `decide` validates the snapshot, saves the deterministic engine's
  decision, logs it and routes to ship, confirmation link, AI call, deposit or review.
- `on_contact_event`: `load_event → post_interaction → act`. `run_contact_event` accepts buyer
  responses, call outcomes and no-response events through the lifecycle functions. Confirmation
  and timer decisions use the existing score; buyer edits retain the lifecycle's rescoring rules.
  This runner is not yet wired to an HTTP endpoint or a scheduled timer.

`app/agents/assessment.py` runs two real ADK `Agent` roles in sequence: `risk_analyst` selects
reasons and `evidence_verifier` checks that proposal. They receive only numeric features,
scoring results, available SHAP contributions and limited order context, without names, phone
numbers, addresses or free text. They may select at most three canonical English reasons
backed by feature values; validation rejects altered wording, unsupported signals and decision
fields. The verifier may only keep or remove the analyst's reasons. No LLM chooses or changes
the score, tier or action. Message composition and voice remain E5 integration work.

`GEMINI_MODEL` selects the assessment model. With it unset, assessment records `disabled` and
the deterministic pipeline continues. Hard-rule and confirmed orders skip the agents; no
candidate evidence records `no_evidence`. Without a trained risk model, the order stays new and
unscored, and no assessment runs. An exhausted daily quota records `quota_exhausted` and the engine decides without Gemini
reasons. A configured assessment failure, invalid output, timeout or changed order snapshot
reaches review before any buyer contact.
If another run or a staff member has already decided the order, the failed intake preserves
that decision instead. This check runs inside the fallback transaction, including its retries.

Set `GEMINI_MODEL` in the service process environment to enable assessment, with authenticated
Vertex AI credentials and the project/location variables documented in `../.env.example`.
SHAP is exact TreeSHAP on the trained classifier and needs no background, so every `model1.pkl` can be
explained. After any change to the feature set, run `codguard-train` once the new code is deployed.

The assessment budget uses atomic claims in the shared `DecisionLog`: at most
`ASSESSMENT_DAILY_LIMIT` assessment runs per UTC day across all shops (default 30, permitted
range 1–30). A claimed run keeps its quota slot if assessment fails. Each assessment allows
two LLM requests, one HTTP attempt per request and a 15-second timeout around the agent workflow.
Assessment failures are not retried. Completed assessment metadata and validated reasons are
stored with scoring and copied to the decision log.

`app/risk/model.py:explain1` computes exact TreeSHAP contributions of every Model 1 feature,
rescaled to the boosted model's probability (before isotonic calibration, which keeps their order
and sign). The scoring snapshot carries them as `scoring.shap`, and the five largest as
`scoring.top_signals` for the API. An explanation error leaves `available: false` and never blocks
scoring. These contributions inform assessment and do not change the deterministic decision.

Contact branches reserve a send and return `mock: true`; the E5 channel integration still needs
to perform the contact and deliver its result to `run_contact_event`. The graphs do not wait for
a buyer to respond.

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
contact events and the second call followed by review. `tests/test_assessment.py` runs both real
ADK agent roles with a fake LLM and checks evidence validation, redaction, budget and timeout.
`tests/test_assessment_pipeline.py` checks assessment before persistence, immutable scoring
inputs and review without contact on errors or stale snapshots. `tests/test_risk.py`
checks SHAP additivity, the top signals and that an explanation error never blocks scoring. `tests/test_intake.py`
checks the automatic intake trigger and returned decision status. These tests use mock contacts
and model responses; they do not establish live Gemini calls, live-channel completion, Gemini
Live compatibility or Cloud Run cold-start performance.

## ADK dependency constraints

`pyproject.toml` allows `google-adk>=2.11,<3`; `uv.lock` currently resolves `2.11.0`. This admits later
2.x releases when the lock is updated and excludes 3.x. Locked installs keep the tested resolution.

ADK 2.11.0 requires `websockets>=15.0.1,<16` and `opentelemetry-api>=1.39,<=1.42.1`.
The resolved `google-genai` 2.30.1 also requires `tenacity<9.2.0`. These upstream constraints remain
even with the wider ADK version range. The compatible locked set includes `websockets` 15.0.1,
`opentelemetry-api` 1.42.1, `tenacity` 9.1.4, `fastapi` 0.141.1 and `google-api-core` 2.34.0;
changing the ADK requirement alone does not restore the newer versions displaced during resolution.

The manifest also allows `shap>=0.48,<1`; the lock resolves SHAP 0.53.0 for the risk explanations.

The E5 Gemini Live client must be tested with this locked set, including `websockets` 15.x, before
claiming compatibility. See `../docs/gemini-live.md` for the Live API configuration requirements.
