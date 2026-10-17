# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, Gemini CLI, Cursor and others) working in this repository. Human contributors should read it too.

## Project

COD Guard scores cash-on-delivery (COD) orders from Vietnamese social-commerce and website sellers for refusal risk (*"bom hàng"*). It explains the risk in plain English and takes the least intrusive action that still protects the seller: ship, send a confirmation link, place an AI confirmation call, require a deposit, or hold the order for review.

It is a prototype for the Google Cloud AI Builder Cup 2026 (Retail & Commerce track).

| Document | Use it for |
|---|---|
| `README.md` | Product overview, architecture, planned layout and setup |
| `COD_Guard_Scope_of_Work.md` | Deliverables, workstreams, milestones, scope cut line, out of scope (Vietnamese) |
| `COD_Guard_Epics.md` | Epics E1–E10 and sub-epics, each with its acceptance criteria ("Done khi"), priority and dependencies (Vietnamese) |

- The "Done khi" column in `COD_Guard_Epics.md` is the acceptance criterion for a piece of work. If it disagrees with this file, the epics file wins; point out the conflict in the PR.
- `COD_Guard_Scope_of_Work.md` and `COD_Guard_Epics.md` are maintained by the repo owner. Change them only when asked.

## Status

The backend and the frontend scaffold exist; most shop screens are still placeholders. The layout and stack below are the plan from `README.md`, and commands marked "Planned" have not been run. When you add the first real code for an area, replace the planned command with the real one, here and in the README, in the same PR. Never document a command you have not run.

## Planned layout

```
api/            OpenAPI contract (generated from backend/, used by frontend/)
backend/        Python service on Cloud Run: API, decision engine, ADK agents
  app/          FastAPI app: routes (api/v1/) and request/response schemas (schemas/)
    decision/   order lifecycle, rescoring, confirmed-order guard (E4.1) and tier policy (E4.2)
    agents/     ADK workflows (E4.7), advisory assessment and the decision log
    calls/      AI calls on the backend: contact rules, call jobs to Pub/Sub, controller results
    demo/       synthetic world of the demo shop's branches, history seed and live simulator
    telephony/  call controller: Pub/Sub consumer, ARI client, call agents (runs on the Asterisk VM)
  config/       rule set YAML; only `tier_policy` is read by the code so far
  scoring/      hard rules, expected loss, model calls
  voice/        Gemini Live session handling
    prompts/    AI call system instruction and the record_call_outcome tool
    scripts/    scripted call: steps, prompts and key map
  tests/
docs/           Technical notes (Gemini Live integration, call controller)
frontend/       Shop web app + buyer confirmation page (Vite + React, served by nginx on Cloud Run)
  src/routes/   TanStack Router file routes; _shop/ is the shop layout, c/ the public buyer page
  src/api/gen/  Hey API client generated from api/openapi.yaml (do not edit)
  src/components/ui/, src/components/reui/  shadcn and ReUI registry components
  src/components/blocks/  ReUI blocks adapted to the app: app-shell-1 (layout), auth-4 (login), wizard-1 (onboarding), dashboard-1 (dashboard, backtest), data-grid-base-1 (orders), receipt-2 (order page), solution-agents-5 and card-2 (review queue), settings-3 (settings, demo), receipt-6 (buyer page)
  src/mocks/    In-browser mock API with seeded synthetic data, used while endpoints return 501
data/seed/      Pseudonymised demo data only
infra/          Deployment and Firebase config; firestore.indexes.json lists the composite indexes the queries need
scripts/        Demo reset, abuse simulation, call test runner
```

## Stack

- Backend: Python 3.11+, ASGI app served by uvicorn (`app.main:app`)
- Frontend: Node.js 20+, pnpm, React 19 + TypeScript on Vite, Tailwind CSS v4, shadcn/ui and ReUI components (style `base-nova`, on Base UI rather than Radix), TanStack Router (file-based) and TanStack Query, Zustand for client state, Hey API for the API client
- Base UI uses `render` instead of `asChild`, `onClick` on menu items instead of `onSelect`, and `items` on a `Select` so it shows labels. Read "Base UI in our code" in `frontend/README.md` before changing UI code.
- Use ReUI's `data-grid` for data tables, not a hand-rolled `<table>`. Install registry components with the shadcn CLI rather than writing or editing them by hand (see `frontend/README.md`).
- Server state lives in TanStack Query through the generated `*Options` helpers; Zustand only holds client state (auth token, theme).
- The login page calls `POST /api/v1/auth/login` (`src/lib/auth.ts`) and keeps the token in the Zustand auth store; a 401 from any call signs the user out.
- AI: Gemini (signal extraction and reasons), Gemini Live API (voice), Agent Development Kit (orchestration)
- Risk model: scikit-learn `HistGradientBoostingClassifier` with isotonic calibration and SHAP (`backend/app/risk/`), one per country, trained by the Cloud Run job `codguard-train` from Firestore and stored in Cloud Storage (`ai-codguard-ml`). No BigQuery.
- Data: Firestore (orders and app state), Cloud Storage (models, monitoring reports)
- Secrets in Secret Manager; region `asia-southeast1`. Exceptions: the Gemini assessment (`GEMINI_MODEL`, `gemini-3.1-flash-lite` in `ci.yml`) calls Vertex AI in `GOOGLE_CLOUD_LOCATION=global`, because that model is not served from `asia-southeast1`; Gemini Live API sessions run in `GEMINI_LIVE_LOCATION` (`us-central1`), because the Live API is not served from Asia regions.
- Model IDs come from environment variables (`GEMINI_MODEL`, `GEMINI_LIVE_MODEL`). Never hard-code them.
- Telephony: Asterisk and the call controller run on the VM `codguard-asterisk` (`us-central1`); the backend sends them call jobs on the Pub/Sub topic `call-jobs`. Read `docs/call-controller.md` before changing call code.
- Before changing voice code or the call prompt, read `docs/gemini-live.md`. Live models changed in September 2026 (`gemini-3.8-live`), and older tutorials use config that 3.8 rejects.
- The pipeline is written against `google-adk` 2.x (`>=2.11,<3` in `backend/pyproject.toml`). ADK 2.0 replaced the template workflows with a graph engine: most tutorials online are still 1.x, and the 1.x pattern (`SequentialAgent`, subclassing `BaseAgent` and overriding `_run_async_impl`) is ignored without an error on 2.x. Use `Workflow` with function nodes.
- ADK caps `websockets` below 16 and `opentelemetry-api` at 1.42.1, and its `google-genai` dependency caps `tenacity` below 9.2. The `opentelemetry-api` cap also holds `fastapi` and `google-api-core` back. The Gemini Live client (E5) therefore runs on `websockets` 15.x.
- ADK runs synchronous nodes on the event loop. The intake route is a sync endpoint, so FastAPI runs it in a worker thread and `asyncio.run` gives each run its own loop there. Do not turn the route into `async def` while the nodes make blocking Firestore calls: they would then block every request on the instance.

## Commands

Backend commands run from `backend/` and need [uv](https://docs.astral.sh/uv/).

| Task | Command |
|---|---|
| Run all dev servers | `make dev` from the repo root: backend :8080 and frontend :5173 with every API call answered by the in-browser mock; `make dev API=backend` sends calls to the backend and mocks only its 501 answers. `make help` lists `install`, `test`, `lint`, `generate`. |
| Install backend dependencies | `uv sync` |
| Backend dev server | `uv run uvicorn app.main:app --reload --port 8080` (docs at `/docs`) |
| Backend tests | `uv run pytest` |
| Inspect the ADK pipeline | `uv run adk web app` (the pipeline is listed as `agents`) |
| Backend lint and format | `uv run ruff check . && uv run ruff format --check .` |
| Export the API contract | `uv run python -m app.openapi_export` (writes `api/openapi.yaml`) |
| Train the risk model | `uv run python -m app.risk.jobs.train [--country VN]` (env `FIRESTORE_DATABASE`, and `MODEL_BUCKET` or a local `MODEL_DIR`); in the cloud: `gcloud run jobs execute codguard-train`. One model per country (`models/{db}/{country}/`), trained on the orders of that country's branches; without `--country` it trains every country. It also stores the country's backtest (`GET /dashboard/backtest?country=`). Run it after every deploy that changes the feature set: scoring fails until a model with the new columns is promoted |
| Monitor the models | `uv run python -m app.risk.jobs.monitor` (same env); in the cloud: Cloud Run job `codguard-monitor`, run daily at 02:00 Vietnam time by the Cloud Scheduler job `codguard-monitor-daily`, which was created in GCP by hand, not by `ci.yml`. Per country it writes an Evidently report and `latest/monitor.json`, which `GET /dashboard/model-health` turns into plain words for the shop owner (`app/risk/health.py`: up to date, or update recommended and why). The owner's **Update model** button (`POST /dashboard/model-health/update`) runs `codguard-train`; `codguard-runtime` has `roles/run.invoker` on that job, granted by hand |
| Export an order history for onboarding | `uv run python -m app.demo.history_csv --days 30 --out history.csv [--seed 11]`: past orders with delivery results for every branch, from the demo world with another seed, in the columns `POST /shop/history` reads. Keep the file out of the repo |
| Seed the demo history | `uv run python -m app.demo.seed --days 90 [--apply]` (env `FIRESTORE_DATABASE`, `PHONE_HASH_KEY`, `PHONE_ENC_KEY`): 90 days of finished orders for every branch, same seed every time; without `--apply` it only prints the counts. Then train |
| Add the inbox sort fields (one-off) | `uv run python -m app.data.backfill_orders [--apply]` (env `FIRESTORE_DATABASE`): adds top-level `cod_amount_vnd` and `risk_score` to orders stored before they existed, so the inbox can sort on them; orders that have them are left alone. Without `--apply` it only counts |
| Encrypt stored phones (one-off) | `uv run python -m app.data.encrypt_phones [--apply]` (env `FIRESTORE_DATABASE`, `PHONE_ENC_KEY`): encrypts the phones of orders and calls stored before encryption; already encrypted values are left alone. Without `--apply` it only counts |
| Simulate orders (demo) | `uv run python -m app.demo.simulate --minutes 10 --orders 60 [--countries VN,SG,PH]` (env `INTAKE_URL`, `INTAKE_API_KEYS`): exactly `--orders` orders per country at random times within `--minutes`; a country's branches share them by their usual volume. In the cloud: `gcloud run jobs execute codguard-simulate --region asia-southeast1 --args=--minutes=10,--orders=60`, stop early with `gcloud run jobs executions cancel <execution>`. Orders come from the same buyers as the history and use each branch's `noagents` test key, which the job reads from Secret Manager: they are scored and decided but skip the Gemini assessment. `--agents` posts with the normal keys, so the agents run and use the daily quota. Never pass keys to the job by hand |
| Build and run the backend image | `docker build -t codguard-backend backend` then `docker run -p 8080:8080 codguard-backend` (from the repo root) |
| Mock API for the frontend | Built in: `src/mocks/` answers 501 endpoints (`VITE_API_MOCK=fallback`, default) or everything (`all`). Prism with the contract's fixed examples: `pnpm mock` from `frontend/` |
| Install frontend dependencies | `pnpm install` (from `frontend/`, as are the frontend commands below) |
| Frontend dev server | `pnpm dev` (http://localhost:5173, proxies `/api` to the backend on :8080; `API_PROXY_TARGET` overrides) |
| Frontend lint, format, types, tests | `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test` |
| Frontend build | `pnpm build` |
| Regenerate the frontend API client | `pnpm generate:api` (writes `frontend/src/api/gen/` from `api/openapi.yaml`) |
| Reset demo data | Planned: `python scripts/reset_demo.py` |
| Deploy | Automatic: every push to `main` that passes CI deploys the backend to Cloud Run (`codguard-api`, project `ai-codguard`, `asia-southeast1`). Do not deploy by hand unless asked. |

## API contract

- The contract is defined in code: Pydantic models in `backend/app/schemas/` and routes in `backend/app/api/v1/`. `api/openapi.yaml` is generated from them and committed.
- Any change to a schema or route must re-export `api/openapi.yaml` and regenerate the frontend client (`pnpm generate:api`) in the same PR. `tests/test_contract.py` fails when the YAML is out of date; the frontend CI job fails when `frontend/src/api/gen/` is.
- Shop app sign-in: `POST /api/v1/auth/login` with the admin account from `ADMIN_USERNAME` / `ADMIN_PASSWORD` (the demo shop) or a shop account from `SHOP_ACCOUNTS` (Secret Manager `shop-accounts`: a JSON list of `username`, `password_hash` from `app.auth.hash_password`, `shop_id`, `name`; a password is never stored); tokens are signed with `AUTH_TOKEN_SECRET`. It stands in for Firebase Auth (E7.1). Every route that reads or changes shop data takes `user: CurrentUser` (`app/api/security.py`) and scopes its work to `user.shop_id`; the router-level `bearer_auth` only declares the scheme.
- Order reads: `GET /orders` pages one shop's orders in Firestore (`app/decision/inbox.py`, `OrderStore.page`): it filters by branch, status, tier and placing time, sorts on top-level fields (`placed_at`, `updated_at`, `risk_score`, `cod_amount_vnd`), reads only the fields a row needs and returns `next_cursor` for the next page; the total is a count aggregation. Never load a shop's orders whole. Each filter and sort combination has its composite index in `infra/firestore.indexes.json`; a new query shape needs its index there. Each deploy from `main` creates the indexes the database lacks; until a new one has built, the query fails with a 500. Search (`q`) is exact: order ID, shop order ID or full phone number (by its hash).
- Review queue: each order in Pending review carries `review_reason` (why it is there: a suggestion waiting for Accept, an invalid phone, no answer to the link, the calls or the deposit, a call that ended unclear or reached the wrong person, attempts used, held by staff, or other), its `hard_rules` and `contact_summary` (the agents' summary of its latest call). `review_reason` is derived from what is stored on the order (`views.review_reason`), so it also holds for orders stored before it existed.
- Overview: `GET /dashboard/summary?from&to&country` counts one country's orders placed in the period from a Firestore projection (`app/decision/dashboard.py`, `OrderStore.select`; index shop_id + branch_id + placed_at). Savings are an estimate from `PREVENTS` (`app/risk/backtest.py`) and the shop's contact costs, counted on the first contact each order got (`intervention.contact_action`), so an unanswered link that later led to review still counts as a link. The frontend mock no longer answers it.
- Routes that are not implemented yet return 501 `not_implemented`. The frontend answers them from its in-browser mock (`frontend/src/mocks/`) until then. When you implement an endpoint, keep the mock's behaviour in line or remove what the backend now covers; the mock must keep following the domain rules below.
- Every schema example must validate against its model (also enforced by the tests), because the mock server returns those examples.
- Endpoints for the call controller have the tag `internal` and accept only a Google ID token of a controller service account. The Pub/Sub call job is documented as the `call-job` webhook. See `docs/call-controller.md`.

## Domain rules

These rules come from the README and the epics. Code and tests must enforce them. If a task seems to require breaking one, stop and raise it in the PR.

### Scoring

- Gemini extracts signals and writes reasons. It never sets or changes the score, the tier or the action.
- At most 3 reasons per order, in English, written by the two advisory agents (`app/agents/assessment.py`) from the evidence, weighed in this order: the business rules that fire on the order (a phone's failed past orders, a new phone, an incomplete address, many orders in 24 hours, a COD far above the phone's usual), the signals that raise the order's risk most (SHAP, with their values), and after an AI call what was said. Each reason cites the evidence keys it rests on; code keeps only reasons whose cited keys exist on the order and whose numbers match that evidence, and drops the rest. When the agents do not run (no `GEMINI_MODEL`, a `noagents` test order, a hard rule, the daily quota used) or keep nothing, the shop sees the business-rule sentences. Target: 0 invented reasons on the 30-order evaluation set.
- After an AI call the buyer spoke on, the same two agents read the stored transcript (the buyer's and recipient's names replaced by "the buyer") and write a summary of the call for the shop, in English, citing the transcript lines it rests on; it replaces the call's `summary_vi`, and the reasons may be refined with what was said. Advisory: a failure leaves the controller's summary and the reasons as they were.
- Hard rules run first:
  - fully prepaid order → skipped;
  - invalid phone number → held for review;
  - phone with a ≥75% return rate over at least 3 past orders → Very High.
- Location may contribute to a score but is never the only reason for High or Very High. The engine checks it (`engine.location_only`): when an order scored with the average province would be below High, its tier is capped at Medium.
- The training label "failed" counts buyer-caused failures only (refused, unreachable), never carrier or shop errors.

### Branches and countries

- The demo shop has branches in Vietnam, Singapore and the Philippines (`backend/config/branches.yaml`). Each intake key belongs to a branch (`key:shop:branch[:noagents]`); intake stores `branch_id`, `country` and `currency` on the order.
- One risk model per country, never trained on another country's orders. A branch uses its country's model; a second branch in a country is one more line in the config.
- Amounts are integers in the currency's minor unit (VND has none; SGD and PHP are in cents). Field names keep the `_vnd` suffix for compatibility. Costs, local time and phone format come from the order's country; a number written in international form (`+84…`, `+65…`, `+63…`) may be of another country the shop serves.
- Tier cut-offs are the same in every country.
- The shop's profile (`GET/PATCH /shop`, Firestore `shops/{shop_id}`, onboarding E7.1) holds its name and, per country, its costs and contact hours. It starts with the country defaults of `branches.yaml` and stores only what the owner changed. Decisions and calls use the shop's values for the order's country: the expected loss is recomputed with the shop's cost of a failed delivery, and the AI call introduces itself with the shop's name. Training and the backtest keep the country defaults.
- Onboarding (`/onboarding`, opened by itself for a shop with no order yet): shop name, costs and contact hours per country, then the shop's past orders with their delivery results (`POST /shop/history`, CSV up to 20,000 rows, checked row by row, stored as finished unscored orders; `app/data/history.py`), then a model update (`POST /dashboard/model-health/update`) with its progress, then the review. Every training run writes `latest/run.json`, so the step also ends for a country whose new model was not better and was not promoted (`last_update.replaced: false`: the model in use stays). History and training can be skipped. The models stay one per country: a shop's history joins the orders that country's model learns from.

### Decisions

- `expected_loss = P(failed delivery) × max(cost of one failed delivery − amount already paid, 0)`: the shop keeps what the buyer paid when the buyer refuses, so a deposit lowers the loss. A fully prepaid order is skipped.
- Contact the buyer only when `expected_loss` is higher than the cost of the contact action.
- Default policy:

  | Tier | Action | If no response |
  |---|---|---|
  | Low | Ship now | — |
  | Medium | Send confirmation link | AI call after 2 hours |
  | High | AI call | Hold for review after the last attempt |
  | Very High | Require deposit | Hold for review if unpaid |

- Order states: New, Cleared to ship, Awaiting confirmation, Awaiting deposit, Pending review, Cancelled, Shipped, Delivered, Delivery failed (in the epics: Mới, Được gửi, Chờ xác nhận, Chờ cọc, Chờ duyệt, Đã hủy, Đã gửi, Giao thành công, Giao thất bại).
- Editing an order before it ships triggers a rescore. A confirmed order is never contacted again.
- A new order runs the pipeline at intake, with no one pressing anything: `load_order → score → assess_order → decide → act`. The assessment uses two advisory agents when `GEMINI_MODEL` is set; it validates evidence-backed reasons before the decision is saved. Only the deterministic engine in `app/decision` picks the action; an LLM may write the wording of a message but never decides.
- Every way out of the pipeline that is not a decision ends in review: a run that still fails after its retries, an action with no branch of its own, and an event the L4 table does not know. Nothing reaches the buyer on an error.
- A send is claimed before it happens, so a retry, a redelivered webhook or a rerun never contacts the buyer twice. A confirmation link or deposit request is claimed under `order_id + action`. Each of the two AI call attempts has its own claim (`order_id:ai_call:1`, `:2`) tied to the decision it carries out, and the attempt is recorded on the order (`attempts.ai_call`) so the no-response timer moves on to the second call or to review.
- A policy change applies only to decisions made after the change.
- Random tests (`random_tests` in the shop's policy, default on): about 12 % of orders whose tier allows more than one action get one at random, so the shop learns what each action prevents (Model 2). The owner can turn them off in Settings → Automation, e.g. for a demo; the tier policy then decides every order. An order whose current action is random shows a "Random test" badge (`random_test`) in the inbox and on its page.
- Automation (`automation` in the shop's policy, `GET/PUT /shop/policy`) is off by default (mode `suggest`): every contact the engine picks (confirmation link, AI call, deposit request) waits in review with `suggested_action` and `block_reasons: [manual_approval]`, and nothing reaches the buyer until the shop accepts it (`POST /orders/{id}/suggestion/accept`; the order then waits for the buyer with the usual no-response timer). The owner switches it on (mode `auto`): links and deposit requests then go out by themselves, and AI calls inside the shop's rules: the lowest risk tier to auto-call, an amount range per currency, sales channels, a call window with days (branch local time), attempts (1 or 2) and the gap between them (at least 30 minutes). A call outside these rules is suggested the same way. Automation never adds a contact: which tiers get one is the tier policy's choice. Contact protection applies on top: automation can narrow it, never widen it. Policy versions are never edited or deleted; restoring an old one saves it again as a new version.
- No-response timers: Cloud Scheduler job `codguard-timers` calls `POST /internal/timers/run` every 5 minutes with an ID token of `codguard-runtime` (created by hand, like `codguard-monitor-daily`). Each order waiting for the buyer whose `decision.next_action_at` has passed runs the pipeline's `no_response` event (`app/decision/timers.py`): the second call after the shop's gap, the call after an unanswered link, review after the last attempt.
- Every manual override records who made it, when, and why, in the audit log.

### Contact protection

| Rule | Default |
|---|---|
| AI calls per phone number, across all shops | At most 1 per 24 hours |
| Orders to the same phone batched into one contact | Within 15 minutes |
| Contact hours | 08:00–21:00, local time of the order's country; the shop may narrow it per country (`PATCH /shop`) |
| Call attempts per order | 2, at least 30 minutes apart (a shop may lower or slow its automatic calls) |
| After *"I didn't order this"* | Block the phone for 30 days, all shops |
| After a confirmed order | Trust the phone for 7 days, same shop |
| Gift orders | Verify with the buyer only, never the recipient |
| Content | Order-related only, never promotional |

### AI call and confirmation page

- What the buyer changes on a call: delivery details (address, recipient, note) apply at once and the order is confirmed; a change of items (quantity, variant) is not applied: the order goes to Pending review with the request listed ("Jacket (S): quantity 2 → 5"), because the shop checks stock first. The voice tool sends `quantity` as an integer and `item_variant` when the order has the same item in several variants; the controller asks the model again when they are missing. Every edit writes what changed, from → to, in the timeline.
- The AI call discloses that it is an automated assistant and names the shop. It reads the order summary, reads any changes back before ending, records a cancellation as soon as the buyer asks for it (a reason only if they gave one, never asked for first), and records exactly one of 7 outcomes: Confirmed, Edited, Cancelled, Not ordered, No answer, Wrong person, Unclear.
- The call's system instruction and its one tool, `record_call_outcome`, live in `backend/voice/prompts/`. The model reports the outcome through the tool. The backend validates it, sets *No answer* itself, and commits *Unclear* when a call that the buyer spoke on ends without a valid outcome.
- During a call, the assistant gives no order details until the person confirms they are the buyer. It never mentions risk, scores or tiers, and never asks for money, OTP codes or bank details.
- The confirmation page needs no login and offers Confirm / Change address / Cancel / *"I didn't order this"*. Personal data is partially masked. The link expires after 48 hours.

## Privacy and secrets

- No real phone numbers, names or addresses anywhere in the repo: seed data, fixtures, tests, screenshots and logs included. Use the synthetic data generator, whose numbers have `000` after the calling code (`+84000…`, `+65000…`, `+63000…`).
- Hash phone numbers wherever they are shared across shops.
- Every phone number stored in Firestore is encrypted (`app/data/phone.py`, AES-GCM, key `PHONE_ENC_KEY` from Secret Manager): orders' `buyer_phone` and `recipient_phone`, and the dialled number of a call. Decrypt only where a person reads it (the order API) or a call dials it. Matching across orders and shops uses the keyed hash, never the ciphertext.
- Secrets live in Secret Manager. Never commit `.env`, keys or tokens; keep `.env.example` up to date instead.
- Cap Gemini calls on public demo paths so judges cannot exhaust the quota (E1.4).

## Language

- Code, identifiers, comments, commit messages and PRs: English.
- Everything the shop and the buyer read is in English: shop UI, buyer confirmation page, AI reasons and call summaries, timeline messages and message previews. The AI call speaks the language of the order's branch: Vietnamese for a branch in Vietnam, English for every other branch, whatever the buyer's phone number (`jobs.call_language`). Amounts are spoken in the order's currency.
- Keep Vietnamese person names and addresses in sample data; they are realistic Vietnam data, not UI copy. Some API fields keep a `_vi` suffix (`message_vi`, `text_vi`, `label_vi`, `summary_vi`) for compatibility with stored data; their content is English.
- Predicted figures in the UI carry the label "estimated". Simulated Zalo ZNS / SMS previews carry the label "mock".

## Scope and timeline

- Milestones: M1 9 Oct · M2 13 Oct (end-to-end flow) · M3 16 Oct evening (feature freeze) · M4 18 Oct (submission). After M3, bug fixes only.
- Build Must items first, then Should. Could items wait until after submission.
- Out of scope for the prototype: contacting buyers of marketplace orders (Shopee, Lazada, TikTok Shop), real Zalo ZNS / SMS, real deposits or payments, ready-made connectors (Pancake, Haravan, Sapo, KiotViet), mobile apps, shop billing, languages other than Vietnamese and English. Add new ideas to the roadmap instead of building them.

## Git workflow

- `main` is the default branch and the deploy branch. Never commit or push to it directly, and never force-push it.
- One branch per change, named `feat/…`, `fix/…`, `docs/…`, `chore/…` or `test/…`. Include the sub-epic ID when there is one, e.g. `feat/e4-3-contact-protection`.
- Commit messages: English, imperative summary of at most 72 characters.
- Every change goes through a PR into `main`. Title it with the sub-epic ID when there is one, e.g. `[E4.3] Contact protection limits`. The body says what changed, how it was tested, and which "Done khi" criteria it meets.
- Keep PRs small: one sub-epic per PR where possible.
- Request review only after the **CI result** check is green on the PR's latest commit (see "CI").

## CI

GitHub Actions runs `.github/workflows/ci.yml` on every PR and on every push to `main`.

| Job | What it checks |
|---|---|
| Backend (lint, tests, API contract) | `uv sync --locked`, `ruff check`, `ruff format --check`, `pytest`. The tests also fail when `api/openapi.yaml` is out of date, is not valid OpenAPI, or has an example that does not match its schema. |
| Frontend (lint, types, tests, build) | `pnpm install --frozen-lockfile`, generated API client matches `api/openapi.yaml`, `oxlint`, `prettier --check`, `tsc -b`, `vitest`, `vite build`. |
| Backend image | Builds `backend/Dockerfile` and smoke-tests the container: `/health`, `/openapi.json`, a 501 stub, non-root user, `PORT` override. On pushes to `main` it also publishes `ghcr.io/beavershydraai/hydraai_codguard/backend` with tags `sha-<commit>` and `main`. |
| Deploy (main only) | Copies the tested image from GHCR to Artifact Registry, deploys it to Cloud Run as `codguard-runtime` together with the jobs `codguard-train` and `codguard-monitor` (as `codguard-trainer`), then checks `/health` on the live URL (not `/healthz`: Cloud Run reserves it). Authenticates with Workload Identity Federation; no GCP key is stored in GitHub. |
| Secret scan (gitleaks) | No keys or tokens in the PR's new commits. |
| No real phone numbers | `.github/scripts/check_phone_numbers.py` on all tracked files. Use `+84000…` in examples; add `pii-allow` on a line only for a false positive. |
| CI result | Passes only when every job above passed. This is the check to require for merging. |

- A review request made while **CI result** is not green is withdrawn with a comment (`.github/workflows/review-gate.yml`). A push that turns CI red also withdraws pending review requests.
- Run the same checks locally before pushing (see "Commands").
- A PR that adds a new area (for example `frontend/`) adds that area's lint, test and build job to `ci.yml` and to the `needs` list of **CI result**.
