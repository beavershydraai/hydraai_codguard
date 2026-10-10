# E3 implementation plan

Implement the supplied [E3 task brief](../../tasks/3-e3-ai-signals-reasons.md)
on the existing `feat/3-e3-ai-signals-reasons` branch. Acceptance criteria remain
those in `COD_Guard_Epics.md`. No API or voice changes are needed.

1. Add the shared asynchronous Gemini wrapper, strict internal models, phone
   masking, versioned prompts, timeouts, per-instance call cap and cap hook,
   bounded input-hash cache, and offline recorded-response tests.
2. Implement deterministic address completeness and flags from extracted parts.
   Normalize only unique matches in an official-source administrative lookup;
   preserve unresolved text. Test old/new parity and ambiguous names.
3. Implement optional conversation signals with delimited, masked input and
   gift-aware name comparison in code. Missing chat produces no signals.
4. Generate reasons from positive model contributions and internal numeric
   facts. Validate citations, numbers, prohibited claims, duplication and the
   non-location rule, retry rejected reasons once, then use trusted templates.
5. Create exactly 30 synthetic orders with answer keys and recorded responses.
   Add separate offline and live evaluation modes with per-case outputs and
   explicit human-review requirements.
6. Add a scoring integration service that skips E3 after hard-rule exits and
   exposes signals without inventing contributions, scores, tiers or actions.
   Update configuration and setup documentation.
7. Run the complete offline test suite, lint/format checks, contract freshness
   test and offline evaluation. Live prompt accuracy and the second-reader
   acceptance check require a configured Google Cloud project and are reported
   separately from offline verification.

Defaults selected from the brief: published signal keys/scales, internal facts
without contract changes, risk-raising explanations only, and template fallback.
Lookup coverage is explicit and conservative; partial ward mergers are ambiguous.
Live and text Gemini clients use separate regions and model variables.
