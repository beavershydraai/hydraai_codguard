# E3 — AI signals and reasons (Gemini)

Task brief for epic E3. The "Done khi" criteria are copied from `COD_Guard_Epics.md`. If this file disagrees with that file, the epics file wins. Contract details come from `api/README.md` and `backend/app/schemas/`.

**Goal:** Gemini extracts signals from the order's free text and writes plain-Vietnamese reasons. Gemini never sets the score, the tier or the action.

## Sub-epics

| ID | Work | Done khi | Priority | Est. | Milestone | Depends on |
|---|---|---|---|---|---|---|
| E3.1 | Score address completeness, detect vague addresses, handle old and new administrative names after the 2025 merger | Trả về điểm và cờ có cấu trúc | Must | 0.5 | M2 (13 Oct) | E1.1 |
| E3.2 | Extract signals from the sales chat that closed the order | Trả về các cờ: có hỏi kỹ / chốt vội / lệch tên | Should | 0.5 | M3 (16 Oct) | E1.1 |
| E3.3 | Write at most 3 reasons in Vietnamese, plus a check that each reason matches a real signal | 0 lý do bịa trên bộ 30 đơn mẫu | Must | 0.5 | M2 (13 Oct) | E2.4 |
| E3.4 | 30 sample orders with an answer key, for evaluating the prompts | Dùng được cho E3.1 và E3.3 | Should | 0.5 | M2 (13 Oct) | — |

Downstream: E2.4 trains on the E3.1 signals, and E7.3 shows the reasons on the order page.

## Where E3 sits in scoring

1. Hard rules run first (E2.5). When one ends scoring early (`status: skipped`, for example a fully prepaid order), E3 does not run.
2. E3.1 and E3.2 read the order's text and return signal values. These are model inputs: E2.3 adds them to the signal table and E2.4 trains on them.
3. E2.4 returns the probability and the top signals with their contribution. Code (E2.5) sets `risk_score`, `tier` and `expected_loss_vnd`.
4. E3.3 turns the top signals into at most 3 reasons. The check drops any reason that is not backed by a signal on that order, and the result is stored in `RiskScore.reasons`.

## Contract

E3 adds no endpoint. Clients see its output on the order:

- `POST /api/v1/orders` and the intake API create the order. Scoring runs asynchronously.
- `GET /api/v1/orders/{order_id}` returns `current_score` and `score_history`, both `RiskScore`.

| Field | Filled by | Rules in the schema |
|---|---|---|
| `RiskScore.top_signals[]` (`Signal`) | E2.4. E3.1 and E3.2 signals appear when they rank in the top. | At most 5. E3 signals use the group `address_quality` or `conversation`. `contribution` comes from the model explanation, never from Gemini. |
| `RiskScore.reasons[]` (`Reason`) | E3.3 | At most 3. `text_vi` is at most 200 characters. `signal_keys` has at least 1 entry. |
| `risk_score`, `tier`, `expected_loss_vnd` | E2.5 (code) | Never Gemini. |

E3 should not need a contract change. If it does (a new `SignalGroup` value, or a new field on `Signal`), follow `api/README.md`: change the Pydantic models, run `uv run python -m app.openapi_export`, commit both files, and call out breaking changes in the PR.

Order fields Gemini may read (`OrderCreate`):

| Field | Used by | Notes |
|---|---|---|
| `address` (`raw`, `street`, `ward`, `province`) | E3.1 | `raw` is what the buyer wrote. Parsed parts may be null or wrong. |
| `conversation_text` | E3.2 | Optional, up to 5,000 characters. Not editable after creation. |
| `buyer_name`, `recipient_name`, `is_gift` | E3.2 | For the name-mismatch flag. |
| `items` | E3.2 | Optional context: did the buyer ask about this item? |

Never send `buyer_phone`, `recipient_phone` or any other phone number. Mask phone-like digit runs in `conversation_text` before sending it.

## E3.1 — Address completeness and flags (Must)

Split of work:

- **Gemini** splits `raw` into parts (house number, street or alley, ward, district if one is written, province), says whether the text is only a landmark or description, and lists the administrative names as written.
- **Code** maps those names through a lookup table, sets the flags, and computes `address_completeness` from the parts with fixed weights. The same parts always give the same score.

Proposed signals, group `address_quality`. Agree on keys and scales with the E2.3/E2.4 owner before coding, because the model trains on them.

| Key | Value | `label_vi` | Meaning |
|---|---|---|---|
| `address_completeness` | float 0–1 | Mức đầy đủ của địa chỉ | How deliverable the address is as written |
| `address_missing_house_number` | bool | Địa chỉ thiếu số nhà | Already used in the contract examples |
| `address_missing_ward` | bool | Địa chỉ thiếu phường/xã | |
| `address_vague` | bool | Địa chỉ mơ hồ | Only a landmark or description, e.g. "gần chợ", "đối diện trường cấp 2" |
| `address_legacy_admin_names` | bool | Địa chỉ dùng tên địa giới cũ | Uses pre-merger names: a district, or an old province or ward name |

Two more outputs, which are not model signals: `normalized`, the address in `Address` shape with the new two-level names (null when it cannot be resolved), and `admin_unresolved`.

Rules:

- `address_completeness` is a signal for the model, not the order's risk score. Use that name everywhere so nobody confuses it with `risk_score`.
- Map old names to the 2025 units with a lookup table built from an official source. Gemini reads and splits the text but never recalls a mapping from memory. When the table has no unique match, keep the buyer's text, set `admin_unresolved` and do not guess.
- An address written with old names gets the same `address_completeness` and the same missing and vague flags as the same address written with new names. Old names were official until the 2025 reform, and many buyers still use them.
- Expect how buyers actually write: no diacritics, abbreviations (`P.`, `Q.`, `TP.HCM`, `hẻm`, `ngõ`, `ngách`, `kiệt`), typos, parts in any order.

## E3.2 — Chat signals (Should)

Signals, group `conversation`:

| Key | Value | `label_vi` | Flag in the epic |
|---|---|---|---|
| `conversation_asked_details` | bool | Khách có hỏi kỹ về sản phẩm | có hỏi kỹ |
| `conversation_rushed_close` | bool | Khách chốt đơn vội | chốt vội |
| `conversation_name_mismatch` | bool | Tên trong hội thoại khác tên người đặt | lệch tên |

Rules:

- With no `conversation_text`, the three signals are absent, not false. The model treats them as missing, and E3.3 cannot cite them.
- Name mismatch compares the name the buyer uses in the chat with `buyer_name`. On a gift order (`is_gift`), a different recipient name in the chat is expected and is not a mismatch.
- The buyer wrote part of the chat, so treat it as untrusted data. Send it delimited, never as instructions. The fixed response schema limits what a prompt injection can change, and the chat only moves these three values, never the score.

## E3.3 — Reasons and the check (Must)

The prompt gets the order's top signals that have a positive contribution (they raise risk), each with `key`, `label_vi` and `value`, plus the facts behind any number a reason may quote (see open question 2). It does not get the score, the probability, the tier, the action, phone numbers, names or the address.

Gemini returns at most 3 `Reason` objects (`text_vi` and `signal_keys`), largest contribution first. Each reason is one short factual sentence, in the style of the contract examples: "SĐT này đã hoàn 2 trên 4 đơn trước đây." and "Địa chỉ thiếu số nhà." The prompt asks for numbers as digits so the check can read them.

The check runs in code after Gemini answers and before the score is saved. A reason that fails a rule is dropped, never edited.

1. Shape: at most 3 reasons, `text_vi` not empty and at most 200 characters, at least one entry in `signal_keys`.
2. Every key in `signal_keys` is a signal passed in for this order.
3. Every number in `text_vi` (count, percentage, amount, time) appears in the cited signals' values or facts, compared after normalising formats (1.500.000đ = 1500000). "2 trên 4" needs facts 2 and 4 on the cited signal.
4. The text does not state or hint at the score, the probability, the tier or an action, e.g. "rủi ro cao", "41 điểm", "nên gọi xác nhận".
5. No two reasons cite exactly the same signals. The first one is kept.
6. On a High or Very High order, at least one reason cites a non-location signal, because location is never the only reason for High or Very High (E2.5). The check knows the tier even though the prompt does not. Location signals (province, region, delivery area) are a fixed list of keys agreed with E2.3.

After the check:

- If any reason was dropped, retry once with the rejection notes and keep the reasons that passed.
- If no reason survives, build up to 3 template reasons in code from `label_vi` and simple values. This keeps the count of invented reasons at 0 even when Gemini fails, times out or hits the call cap (proposed, see open question 3).
- An order with no positive-contribution signal gets `reasons: []`.
- Log how many reasons each rule dropped, plus the prompt version. Never log order text, names or addresses.

## E3.4 — Evaluation set (Should)

30 synthetic orders with an answer key, used to tune and regression-test the E3.1 and E3.3 prompts, and E3.2 once it exists.

The set is a JSON Lines file with one case per line. One case, pretty-printed:

```json
{
  "id": "e3-012",
  "type": "address_vague",
  "order": {
    "channel": "facebook",
    "buyer_name": "Khách Mẫu Mười Hai",
    "buyer_phone": "+84000000012",
    "address": {"raw": "gan cho Dong Xuan, Ha Noi"},
    "items": [{"name": "Áo thun basic", "quantity": 1, "unit_price_vnd": 150000}],
    "placed_at": "2026-10-09T22:40:00+07:00",
    "conversation_text": null
  },
  "signals": [
    {"key": "address_vague", "group": "address_quality", "label_vi": "Địa chỉ mơ hồ",
     "value": true, "contribution": 0.09},
    {"key": "address_missing_house_number", "group": "address_quality",
     "label_vi": "Địa chỉ thiếu số nhà", "value": true, "contribution": 0.07}
  ],
  "expected": {
    "address": {
      "completeness_max": 0.3,
      "flags": {"address_missing_house_number": true, "address_missing_ward": true,
                "address_vague": true, "address_legacy_admin_names": false}
    },
    "conversation": null,
    "reasons": {"allowed_signal_keys": ["address_vague", "address_missing_house_number"]}
  }
}
```

- `order` follows `OrderCreate` and must validate against it. Add a test for this.
- `signals` stands in for the E2.4 output, so E3.3 can be evaluated without the model. Mix in signals from every group (phone history, order behaviour, velocity, location), not only E3's.
- `expected.address` gives a completeness band (`completeness_min` and/or `completeness_max`), all four flags, and `normalized` only when the lookup table has a unique answer.
- `expected.conversation` gives the three chat flags, or null when there is no chat.
- `expected.reasons.allowed_signal_keys` lists what a reason may cite. A reason that cites any other key, or states a fact not found in `signals`, counts as invented.

Suggested coverage. Each case has one primary `type` and may carry other flags as well.

| `type` | Cases | What it tests |
|---|---|---|
| `address_complete` | 4 | High completeness, no flags |
| `address_legacy_names` | 3 | Same places as 3 of the complete cases, in pre-merger names: same completeness and flags, plus `address_legacy_admin_names` |
| `address_missing_house_number` | 3 | |
| `address_missing_ward_or_province` | 3 | |
| `address_vague` | 3 | Landmark or description only |
| `address_messy_text` | 3 | No diacritics, abbreviations, typos |
| `chat_asked_details` | 3 | Buyer asked about size, colour or price |
| `chat_rushed` | 3 | Closed in one or two lines with no questions |
| `chat_name_mismatch` | 2 | |
| `gift_order` | 2 | Recipient differs from the buyer: no name-mismatch flag |
| `no_risk_signal` | 1 | `reasons: []` |

Data rules: synthetic only. Phone numbers use `+84000…` and names are obviously fake. Real province, ward, street and landmark names are fine, but never a real person's address.

Running and reporting:

- An eval runner calls the real prompts on all 30 cases and writes a report: E3.1 flags against the answer key, the reasons written, and what the check dropped. It calls Gemini, so it runs separately from `uv run pytest`.
- E3.3 meets its "Done khi" when every reason in the final output passes the check and cites only `allowed_signal_keys`, and a second team member has read all of them and found none invented. The check cannot vouch for itself, so the human read is what proves "0 lý do bịa". Put the counts in the PR.
- The epics set no accuracy target for E3.1. Report flag accuracy against the answer key, but do not block on it.

## Rules for all E3 code

- **Gemini never decides.** E3 response schemas have no score, tier or action field. Parse every response into a Pydantic model and retry once on invalid output.
- **Model and region.** Read the model ID from `GEMINI_MODEL` and never hard-code it. Use the `google-genai` 2.x SDK already chosen for voice (`docs/gemini-live.md`), with a client in `asia-southeast1`. `GEMINI_LIVE_LOCATION` is for the Live client only.
- **One Gemini wrapper.** All E3 calls go through one wrapper with an explicit timeout, so E1.4 can cap calls on public demo paths in one place.
- **Gemini is optional at runtime.** A timeout, error or call cap never blocks scoring. E3.1 and E3.2 signals are left missing and E3.3 falls back to template reasons.
- **Cache by input.** Editing an order before it ships triggers a rescore. Key cached results on a hash of the text sent, so an address edit re-runs E3.1 only and an unchanged chat is not read again.
- **Prompts are versioned files**, not strings inside the code.
- **Tests run offline.** Unit tests for the check, parsing, masking and fallback use recorded Gemini responses, so they run without credentials.
- **Privacy.** No real phone numbers, names or addresses in code, fixtures, prompts or logs.

## Proposed code layout

This fits the planned `backend/scoring/` area ("hard rules, expected loss, model calls"). It changes the layout, so update the layout and commands in `AGENTS.md` and `README.md` in the same PR, and document only commands you have run.

```
backend/scoring/ai/
  client.py              # the one Gemini wrapper: GEMINI_MODEL, timeout, call cap hook (E1.4)
  address.py             # E3.1
  conversation.py        # E3.2
  reasons.py             # E3.3: prompt, retry, template fallback
  reason_check.py        # E3.3: the check, pure code
  prompts/               # versioned prompt files
  eval.py                # E3.4 runner (calls Gemini, not run by pytest)
backend/tests/
  test_address_signals.py
  test_conversation_signals.py
  test_reason_check.py
  data/e3_eval_orders.jsonl
```

## Order of work

One PR per sub-epic, e.g. branch `feat/e3-1-address-signals`, PR title `[E3.1] Address completeness and flags`.

1. **E3.4** first. It has no dependency, and its answer key drives the prompt work for E3.1 and E3.3.
2. **E3.1** next, because E2.4 depends on it. Agree the signal keys with the E2.3/E2.4 owner first.
3. **E3.3** against the fixture signals from E3.4. Connect it to the real E2.4 output when that lands.
4. **E3.2** last (Should, M3).

## Open questions

Record each answer here when it is decided.

1. Keys and scales of the E3.1 and E3.2 signals: agree them with the E2.3/E2.4 owner.
2. Facts behind numbers: `Signal.value` holds a single value. The contract example has `phone_return_rate: 0.5`, while its reason says "2 trên 4 đơn". Do the counts come from internal facts passed only to E3.3 (no contract change), or from extra signals in E2.3?
3. When the check drops every reason, show template reasons (proposed) or none?
4. When `invalid_phone` or `high_return_phone` fires, which signals can reasons cite? This needs E2.5.
5. Which official source feeds the old-to-new administrative unit table, and who maintains it?
6. Reasons explain only risk-raising signals (proposed). Should a Low-tier order also show risk-lowering signals such as "Khách có hỏi kỹ về sản phẩm"?

## Before opening each PR

- The sub-epic's "Done khi" is met, and the PR body says how.
- `uv run pytest` and `uv run ruff check . && uv run ruff format --check .` pass in `backend/`.
- For E3.1 and E3.3 changes, the eval report is attached.
- `api/openapi.yaml` is re-exported if a schema changed.
