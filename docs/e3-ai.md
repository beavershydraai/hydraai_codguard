# E3 AI signals and reasons

The implementation follows [the E3 brief](../tasks/3-e3-ai-signals-reasons.md).
The Gemini Live notes supply the shared SDK choice, `google-genai>=2.29,<3`,
and the separation between text and Live regions. E3 adds no endpoint and
does not change the OpenAPI contract. API routes remain stubs until E2/intake
and persistence connect the scoring pipeline.

## Configuration

Set `GOOGLE_CLOUD_PROJECT` and `GEMINI_MODEL` in the process environment.
The SDK uses Application Default Credentials / the Cloud Run service account,
not an API key. `.env.example` documents the variables; copying it alone does
not load environment variables into Python. Step-by-step setup and live checks
are in [gemini-test-guide.md](gemini-test-guide.md) (Vietnamese).

Text calls use a separate client in `asia-southeast1`. E3 never reads
`GEMINI_LIVE_MODEL` or `GEMINI_LIVE_LOCATION`. The SDK configuration follows
the [official Google Gen AI documentation](https://googleapis.github.io/python-genai/).

`GEMINI_TIMEOUT_SECONDS` defaults to 10 per attempt. Invalid structured
responses retry once; timeouts and SDK failures return missing features.
`GEMINI_MAX_CALLS` defaults to 100 per reused client instance, including
retries. E1.4 must supply `allow_call` to reserve shared visitor/day quotas;
the local cap alone does not enforce limits across Cloud Run workers.
SDK automatic retries are disabled so every request passes this gateway.

Successful responses are cached in memory by SHA-256 of model, prompt contents,
response schema and the exact masked payload. The cache holds at most 256
entries by default; errors are not cached. Reuse the client across rescoring
runs and close it with `await client.aclose()` when the worker shuts down.
Prompts are versioned files in `backend/scoring/ai/prompts/`.

## Integration

```python
from scoring.ai.client import GeminiClient
from scoring.ai.service import AIService

client = GeminiClient(allow_call=reserve_demo_budget)
ai = AIService(client)

# E2 hard rules decide whether scoring ends early.
features = await ai.extract(order, skipped=hard_rules_skipped)
# E2 consumes features.signals. They have no contribution field.
# E2 produces RiskScore with its own probability, contributions and tier.
explained_score = await ai.explain(
    model_score,
    facts={"phone_return_rate": {"returned_orders": 2, "past_orders": 4}},
)
```

`reserve_demo_budget` is an E1.4 synchronous callback returning a boolean.
It is called before every actual request; cached results use no quota.
An integration can omit it while using the local cap. `AIService.explain`
returns a copy, changing only reasons. Skipped scores never call Gemini.
Numeric facts are internal, scoped by signal key and never added to the API.

Address analysis returns five fixed-key signals, an optional normalized
`Address`, and `admin_unresolved`. Administrative normalization uses a
conservative lookup built from official sources, never Gemini's memory.
Lookup coverage and weights are documented alongside the address module.
An unresolved mapping preserves buyer text; it does not create missing/vague
flags merely because a buyer used an old administrative name.

Conversation analysis returns three fixed-key signals or `None` when chat
is absent or Gemini fails. Name comparison runs in code and permits the
gift recipient's name. Buyer/recipient phone fields are never sent; phone-like
digit runs in every supplied free-text field are masked.

## Explanations and acceptance

Reasons explain positive model contributions only. The prompt does not receive
the score, probability, tier, action, buyer names, address or phone fields.
The checker rejects malformed reasons, unknown citations, unsupported numbers,
prohibited claims and repeated citation sets. High/Very High explanations
must include a non-location signal. Template fallback uses trusted signal
definitions and passes through the same check. No positive signals gives `[]`.

The fixed signal keys and location key list are implementation defaults from
the brief, ready for E2.3/E2.4 integration review. Numeric facts remain internal.
Safe templates are the fallback; explanations do not include risk-lowering
signals. String-valued signals and unregistered keys are omitted from reason
prompts. `REASON_SIGNAL_KEYS` defines the permitted numeric/boolean signals;
`REASON_FACT_KEYS` permits `past_orders` and `returned_orders` for phone history
and `time_window_hours` for the phone's order count. E2 must register new trusted
keys, fact names and templates when extending the explanation vocabulary.
Logs contain event/drop counts and prompt versions, never order text,
names, addresses or exception messages.

Automated citation and numeric checks cannot prove every sentence's semantics.
The live evaluation and a second team member reading all final reasons are
still required to establish E3.3's “0 invented reasons” acceptance criterion.
Offline recordings verify code behavior, not live prompt accuracy.

## Evaluation

From `backend/`, the verified offline command is:

```bash
uv run python -m scoring.ai.eval --offline --output ../docs/evaluations/e3-offline.json
```

The [recorded report](evaluations/e3-offline.json) has 30 cases, 120/120 matching
address flags, 30/30 completeness bands, 30/30 chat flags, and 21 final reasons
passing the machine checks with no disallowed citations. Four candidate reasons
were rejected. These numbers measure recorded-response regression behavior.

The runner's `--help` explains `--input`, `--output` and `--offline`. Omitting
`--offline` uses the real Gemini prompts after checking project/model configuration.
Live runs with timeouts, caps, missing extractions or failed gateway requests are
marked incomplete; template fallback cannot turn them into live acceptance.
Review all final sentences in the resulting report with a second team member.
