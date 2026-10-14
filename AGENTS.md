# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, Gemini CLI, Cursor and others) working in this repository. Human contributors should read it too.

## Project

COD Guard scores cash-on-delivery (COD) orders from Vietnamese social-commerce and website sellers for refusal risk (*"bom hàng"*). It explains the risk in plain Vietnamese and takes the least intrusive action that still protects the seller: ship, send a confirmation link, place an AI confirmation call, require a deposit, or hold the order for review.

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
  config/       rule set YAML; only `tier_policy` is read by the code so far
  scoring/      hard rules, expected loss, model calls
  voice/        Gemini Live session handling
    prompts/    AI call system instruction and the record_call_outcome tool
  tests/
docs/           Technical notes (Gemini Live integration)
frontend/       Shop web app + buyer confirmation page (Vite + React, Firebase Hosting)
  src/routes/   TanStack Router file routes; _shop/ is the shop layout, c/ the public buyer page
  src/api/gen/  Hey API client generated from api/openapi.yaml (do not edit)
  src/components/ui/, src/components/reui/  shadcn and ReUI registry components
  src/components/blocks/  ReUI blocks adapted to the app: app-shell-1 (shop layout), auth-4 (login)
ml/             Data prep, synthetic data generator, BigQuery ML SQL, backtest
data/seed/      Pseudonymised demo data only
infra/          Deployment and Firebase config
scripts/        Demo reset, abuse simulation, call test runner
```

## Stack

- Backend: Python 3.11+, ASGI app served by uvicorn (`app.main:app`)
- Frontend: Node.js 20+, pnpm, React 19 + TypeScript on Vite, Tailwind CSS v4, shadcn/ui and ReUI components, TanStack Router (file-based) and TanStack Query, Zustand for client state, Hey API for the API client
- Use ReUI's `data-grid` for data tables, not a hand-rolled `<table>`. Install registry components with the shadcn CLI rather than writing or editing them by hand (see `frontend/README.md`).
- Server state lives in TanStack Query through the generated `*Options` helpers; Zustand only holds client state (auth token, theme).
- Sign-in is a development stub until Firebase Auth lands (E7.1): `src/lib/auth.ts` stores `VITE_DEV_AUTH_TOKEN`. Never set that variable in a production build.
- AI: Gemini (signal extraction and reasons), Gemini Live API (voice), Agent Development Kit (orchestration)
- Data: BigQuery ML boosted trees (risk model), BigQuery (training data, analytics), Firestore (app state)
- Secrets in Secret Manager; region `asia-southeast1`. Exception: Gemini Live API sessions run in `GEMINI_LIVE_LOCATION` (`us-central1`), because the Live API is not served from Asia regions.
- Model IDs come from environment variables (`GEMINI_MODEL`, `GEMINI_LIVE_MODEL`). Never hard-code them.
- Before changing voice code or the call prompt, read `docs/gemini-live.md`. Live models changed in September 2026 (`gemini-3.8-live`), and older tutorials use config that 3.8 rejects.
- The pipeline is written against `google-adk` 2.x (`>=2.11,<3` in `backend/pyproject.toml`). ADK 2.0 replaced the template workflows with a graph engine: most tutorials online are still 1.x, and the 1.x pattern (`SequentialAgent`, subclassing `BaseAgent` and overriding `_run_async_impl`) is ignored without an error on 2.x. Use `Workflow` with function nodes.
- ADK caps `websockets` below 16 and `opentelemetry-api` at 1.42.1, and its `google-genai` dependency caps `tenacity` below 9.2. The `opentelemetry-api` cap also holds `fastapi` and `google-api-core` back. The Gemini Live client (E5) therefore runs on `websockets` 15.x.
- ADK runs synchronous nodes on the event loop. The intake route is a sync endpoint, so FastAPI runs it in a worker thread and `asyncio.run` gives each run its own loop there. Do not turn the route into `async def` while the nodes make blocking Firestore calls: they would then block every request on the instance.

## Commands

Backend commands run from `backend/` and need [uv](https://docs.astral.sh/uv/).

| Task | Command |
|---|---|
| Run all dev servers | `make dev` from the repo root: backend :8080, Prism mock :4010, frontend :5173 calling the mock; `make dev API=backend` points the frontend at the backend. `make help` lists `install`, `test`, `lint`, `generate`. |
| Install backend dependencies | `uv sync` |
| Backend dev server | `uv run uvicorn app.main:app --reload --port 8080` (docs at `/docs`) |
| Backend tests | `uv run pytest` |
| Inspect the ADK pipeline | `uv run adk web app` (the pipeline is listed as `agents`) |
| Backend lint and format | `uv run ruff check . && uv run ruff format --check .` |
| Export the API contract | `uv run python -m app.openapi_export` (writes `api/openapi.yaml`) |
| Train the risk model | `uv run python -m app.risk.jobs.train` (env `FIRESTORE_DATABASE`, and `MODEL_BUCKET` or a local `MODEL_DIR`); in the cloud: `gcloud run jobs execute codguard-train` |
| Monitor the models | `uv run python -m app.risk.jobs.monitor` (same env); in the cloud: Cloud Run job `codguard-monitor`, daily |
| Build and run the backend image | `docker build -t codguard-backend backend` then `docker run -p 8080:8080 codguard-backend` (from the repo root) |
| Mock API for the frontend | `pnpm mock` from `frontend/` (Prism, pinned in `package.json`), or `npx @stoplight/prism-cli mock api/openapi.yaml` from the repo root |
| Install frontend dependencies | `pnpm install` (from `frontend/`, as are the frontend commands below) |
| Frontend dev server | `pnpm dev` (http://localhost:5173, proxies `/api` to the Prism mock on :4010; `API_PROXY_TARGET` overrides) |
| Frontend lint, format, types, tests | `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test` |
| Frontend build | `pnpm build` |
| Regenerate the frontend API client | `pnpm generate:api` (writes `frontend/src/api/gen/` from `api/openapi.yaml`) |
| Reset demo data | Planned: `python scripts/reset_demo.py` |
| Deploy | Automatic: every push to `main` that passes CI deploys the backend to Cloud Run (`codguard-api`, project `ai-codguard`, `asia-southeast1`). Do not deploy by hand unless asked. |

## API contract

- The contract is defined in code: Pydantic models in `backend/app/schemas/` and routes in `backend/app/api/v1/`. `api/openapi.yaml` is generated from them and committed.
- Any change to a schema or route must re-export `api/openapi.yaml` and regenerate the frontend client (`pnpm generate:api`) in the same PR. `tests/test_contract.py` fails when the YAML is out of date; the frontend CI job fails when `frontend/src/api/gen/` is.
- Shop app sign-in: `POST /api/v1/auth/login` with the one admin account from `ADMIN_USERNAME` / `ADMIN_PASSWORD`; tokens are signed with `AUTH_TOKEN_SECRET`. It stands in for Firebase Auth (E7.1). Every route that reads or changes shop data takes `user: CurrentUser` (`app/api/security.py`) and scopes its work to `user.shop_id`; the router-level `bearer_auth` only declares the scheme.
- Routes that are not implemented yet return 501 `not_implemented`. The frontend works against the Prism mock until then; see `api/README.md`.
- Every schema example must validate against its model (also enforced by the tests), because the mock server returns those examples.

## Domain rules

These rules come from the README and the epics. Code and tests must enforce them. If a task seems to require breaking one, stop and raise it in the PR.

### Scoring

- Gemini extracts signals and writes reasons. It never sets or changes the score, the tier or the action.
- At most 3 reasons per order, in Vietnamese, each backed by a signal actually present on the order. A check rejects reasons that do not match a real signal. Target: 0 invented reasons on the 30-order evaluation set.
- Hard rules run first:
  - fully prepaid order → skipped;
  - invalid phone number → held for review;
  - phone with a ≥75% return rate over at least 3 past orders → Very High.
- Location may contribute to a score but is never the only reason for High or Very High.
- The training label "failed" counts buyer-caused failures only (refused, unreachable), never carrier or shop errors.

### Decisions

- `expected_loss = P(failed delivery) × cost of one failed delivery`, based on the amount still to collect after any deposit.
- Contact the buyer only when `expected_loss` is higher than the cost of the contact action.
- Default policy:

  | Tier | Action | If no response |
  |---|---|---|
  | Low | Ship now | — |
  | Medium | Send confirmation link | AI call after 2 hours |
  | High | AI call | Hold for review after the last attempt |
  | Very High | Require deposit | Hold for review if unpaid |

- Order states: Mới, Được gửi, Chờ xác nhận, Chờ cọc, Chờ duyệt, Đã hủy, Đã gửi, Giao thành công, Giao thất bại.
- Editing an order before it ships triggers a rescore. A confirmed order is never contacted again.
- A new order runs the pipeline at intake, with no one pressing anything: `load_order → score → assess_order → decide → act`. The assessment uses two advisory agents when `GEMINI_MODEL` is set; it validates evidence-backed reasons before the decision is saved. Only the deterministic engine in `app/decision` picks the action; an LLM may write the wording of a message but never decides.
- Every way out of the pipeline that is not a decision ends in review: a run that still fails after its retries, an action with no branch of its own, and an event the L4 table does not know. Nothing reaches the buyer on an error.
- A send is claimed before it happens, so a retry, a redelivered webhook or a rerun never contacts the buyer twice. A confirmation link or deposit request is claimed under `order_id + action`. Each of the two AI call attempts has its own claim (`order_id:ai_call:1`, `:2`) tied to the decision it carries out, and the attempt is recorded on the order (`attempts.ai_call`) so the no-response timer moves on to the second call or to review.
- A policy change applies only to decisions made after the change.
- Every manual override records who made it, when, and why, in the audit log.

### Contact protection

| Rule | Default |
|---|---|
| AI calls per phone number, across all shops | At most 1 per 24 hours |
| Orders to the same phone batched into one contact | Within 15 minutes |
| Contact hours | 08:00–21:00, Vietnam time (`Asia/Ho_Chi_Minh`) |
| Call attempts per order | 2, at least 30 minutes apart |
| After *"Tôi không đặt"* | Block the phone for 30 days, all shops |
| After a confirmed order | Trust the phone for 7 days, same shop |
| Gift orders | Verify with the buyer only, never the recipient |
| Content | Order-related only, never promotional |

### AI call and confirmation page

- The AI call discloses that it is an automated assistant and names the shop. It reads the order summary, reads any changes back before ending, and records exactly one of 7 outcomes: Xác nhận, Đã sửa, Hủy, Không đặt, Không nghe máy, Nhầm người, Không rõ.
- The call's system instruction and its one tool, `record_call_outcome`, live in `backend/voice/prompts/`. The model reports the outcome through the tool. The backend validates it, sets *Không nghe máy* itself, and commits *Không rõ* when a call that the buyer spoke on ends without a valid outcome.
- During a call, the assistant gives no order details until the person confirms they are the buyer. It never mentions risk, scores or tiers, and never asks for money, OTP codes or bank details.
- The confirmation page needs no login and offers Xác nhận / Sửa địa chỉ / Hủy / *"Tôi không đặt"*. Personal data is partially masked. The link expires after 48 hours.

## Privacy and secrets

- No real phone numbers, names or addresses anywhere in the repo: seed data, fixtures, tests, screenshots and logs included. Use the synthetic data generator.
- Hash phone numbers wherever they are shared across shops.
- Secrets live in Secret Manager. Never commit `.env`, keys or tokens; keep `.env.example` up to date instead.
- Cap Gemini calls on public demo paths so judges cannot exhaust the quota (E1.4).

## Language

- Code, identifiers, comments, commit messages and PRs: English.
- Shop UI, buyer confirmation page, AI reasons and call scripts: Vietnamese, with English available for the demo call.
- Predicted figures in the UI carry the label "ước tính". Simulated Zalo ZNS / SMS previews carry the label "mock".

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
