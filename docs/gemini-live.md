# Gemini Live API for the AI confirmation call

Research notes and integration rules for the voice workstream (E5). Checked on 8 October 2026. The Live API changes often, so re-check the model page before you change the model or the session config.

- System instruction: [backend/voice/prompts/confirmation_call.md](../backend/voice/prompts/confirmation_call.md)
- Tool declaration: [backend/voice/prompts/record_call_outcome.json](../backend/voice/prompts/record_call_outcome.json)

## Decisions

| Topic | Decision | Reason |
|---|---|---|
| Model (`GEMINI_LIVE_MODEL`) | `gemini-3.8-live` | GA on Agent Platform since 24 Sep 2026 and Google's default low-latency voice model. Vietnamese (`vi-VN`) is a supported language. |
| Fallback model | `gemini-live-2.5-flash-native-audio` | GA, but retires on 13 Dec 2026. Use it only if 3.8 Live fails the spike. |
| Platform | Gemini Enterprise Agent Platform (formerly Vertex AI), with the project's service account | Same project and credits as the rest of the stack, no API key to manage. |
| Location (`GEMINI_LIVE_LOCATION`) | `us-central1` | Live models are not served from `asia-southeast1` or the `global` endpoint. 3.8 Live runs only in `us`, `eu` and `us-central1`. |
| SDK | `google-genai>=2.29,<3` (Python) | 2.x speaks the 3.8 Live protocol. Version 3.0 removes `session.send()` and `LiveConnectConfig.generation_config`. |
| Topology | Softphone, browser or phone ⇄ Asterisk ⇄ call controller on the Asterisk VM (`us-central1`) ⇄ Live API. See [call-controller.md](call-controller.md). | Credentials, order data and the tool stay server-side, the session runs in the Live API's region, and the backend enforces call caps (E1.4) before it publishes a call. |
| Orchestration | A plain `google-genai` session in `backend/voice/`. ADK only starts the call (E4.7). | ADK's Live docs list the 2.5 and 3.1 Live models but not 3.8 yet, and the outcome tool needs custom handling anyway. |
| Outcome tool | `record_call_outcome`, declared `BLOCKING` | The server cancels a blocking call when the buyer starts talking, so a half-made decision is never recorded. |

## Models

| Model ID | Status | Notes |
|---|---|---|
| `gemini-3.8-live` | GA on Agent Platform, stable on the Gemini API | Use this. 128K input and 64K output tokens. Function calling, Google Search grounding, input and output transcription. |
| `gemini-3.8-live-extended-thinking` | Gemini API | Reasons in the background while speaking fillers. Not needed for a short scripted call, and it accepts only `NON_BLOCKING` tools. |
| `gemini-live-2.5-flash-native-audio` | GA, retires 13 Dec 2026 | Fallback only. US and EU regions. |
| `gemini-3.1-flash-live-preview`, `gemini-2.5-flash-native-audio-preview-*`, `gemini-live-2.5-flash-preview`, `gemini-2.0-flash-live-001` | Legacy | Do not use. Most tutorials target these, and their config breaks on 3.8. |

What 3.8 Live changes compared with older tutorials:

- Do not set `thinking_config`. 3.8 Live does not support `thinking_level`.
- Do not set `enable_affective_dialog` or `proactivity`. Both behaviours are built in. Proactive audio means the model ignores background chatter and answers only when spoken to; setting `proactive_audio: false` returns an error.
- Function calls are `NON_BLOCKING` by default, so declare `behavior` explicitly.
- `send_client_content` works for the whole session, with role `user` or `model`. `turn_complete=True` interrupts whatever the model is saying.
- Send audio with `send_realtime_input(audio=...)`, never `media=`.
- Interruptions are polite: a tool response waits until the buyer pauses.
- The model's knowledge stops in January 2025, so it does not know Vietnam's 2025 province and ward mergers. The instruction tells it not to correct place names. Address checks happen in the backend (E3.1) after the call.

## Where it runs

- The rest of the stack stays in `asia-southeast1`. Only the Live client uses `GEMINI_LIVE_LOCATION=us-central1`. Create a separate `genai.Client` for it rather than changing `GOOGLE_CLOUD_LOCATION` for other Gemini calls.
- The Live session runs in the call controller on the Asterisk VM, also in `us-central1`, so turns do not go through Singapore. Measure the latency from Vietnam in the spike.
- Audio and order details are processed in the US. That is fine for pseudonymised demo data. A production rollout needs a cross-border transfer review under Vietnam's personal data protection law.
- Agent Platform allows up to 1,000 concurrent Live sessions per project.
- The backend on Cloud Run does not hold the call open; the controller does. Cloud Run would cut a WebSocket at its request timeout and bill the instance as active for the whole call.

## Session setup

Checked against `google-genai` 2.29.0: the tool JSON and this config validate.

```python
import json
import os
from pathlib import Path

from google import genai
from google.genai import types

PROMPTS = Path(__file__).parent / "prompts"

client = genai.Client(
    enterprise=True,
    project=os.environ["GOOGLE_CLOUD_PROJECT"],
    location=os.environ["GEMINI_LIVE_LOCATION"],
)

record_call_outcome = types.FunctionDeclaration.model_validate(
    json.loads((PROMPTS / "record_call_outcome.json").read_text(encoding="utf-8"))
)


def render_instruction(order_context: dict, language: str) -> str:
    template = (PROMPTS / "confirmation_call.md").read_text(encoding="utf-8")
    # Insert the order data last, so text typed by buyers is never treated as a placeholder.
    return template.replace("{{call_language}}", language).replace(
        "{{order_context}}", json.dumps(order_context, ensure_ascii=False, indent=2)
    )


def live_config(order_context: dict, language: str = "ENGLISH") -> types.LiveConnectConfig:
    code = "vi-VN" if language == "VIETNAMESE" else "en-US"
    items = [item["name"] for order in order_context["orders"] for item in order["items"]]
    return types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        system_instruction=render_instruction(order_context, language),
        speech_config=types.SpeechConfig(
            language_code=code,
            voice_config=types.VoiceConfig(
                # Placeholder: pick the voice in the E5.1 spike.
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore"),
            ),
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(
            language_codes=[code],
            # Biases speech recognition; up to 1,000 terms.
            custom_vocabulary=[order_context["shop_name"], *items],
        ),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        tools=[types.Tool(function_declarations=[record_call_outcome])],
    )


async def run_call(order_context: dict) -> None:
    async with client.aio.live.connect(
        model=os.environ["GEMINI_LIVE_MODEL"], config=live_config(order_context)
    ) as session:
        ...  # see "Call flow"
```

- Leave voice activity detection on its defaults first. If the model cuts buyers off while they read out an address, set `end_of_speech_sensitivity=END_SENSITIVITY_LOW` or raise `silence_duration_ms` in `realtime_input_config.automatic_activity_detection`. Either adds latency to every turn.
- Skip context window compression and session resumption. A call lasts a few minutes, well under the session limits below.
- There are 30 prebuilt voices. Choose one in the spike.

## Order context

The backend renders one JSON object into the instruction for each call. Pseudonymised example:

```json
{
  "shop_name": "Tiệm Mẫu",
  "buyer": {"full_name": "Nguyễn Thị B", "salutation": "chị"},
  "orders": [
    {
      "ref": "4721",
      "placed_at_spoken": "tối ngày 7 tháng 10",
      "items": [
        {"name": "Áo khoác gió", "variant": "màu đen, size M", "quantity": 1},
        {"name": "Mũ lưỡi trai", "variant": "màu be", "quantity": 2}
      ],
      "cod_amount_spoken": "bốn trăm năm mươi nghìn đồng",
      "deposit_paid_spoken": "",
      "recipient_name": "Nguyễn Thị B",
      "delivery_address": "Số 12 ngõ 34 phố Mẫu, phường Thử Nghiệm, Hà Nội",
      "is_gift": false,
      "expected_delivery_spoken": "2 đến 3 ngày sau khi gửi hàng"
    }
  ],
  "total_cod_amount_spoken": "bốn trăm năm mươi nghìn đồng"
}
```

| Field | Meaning |
|---|---|
| `shop_name` | Said in the opening |
| `buyer.full_name` | Name on the order, used for the identity check |
| `buyer.salutation` | `"anh"` or `"chị"` when the shop knows it, otherwise `""`. The model then says "quý khách" until the buyer's own words show the right form. |
| `orders[].ref` | Short code the buyer can recognise. The model uses it in `changes[].order_ref`. |
| `orders[].items[]` | `name`, `variant`, `quantity` |
| `orders[].cod_amount_spoken` | Amount still to collect, in words |
| `orders[].deposit_paid_spoken` | Deposit already paid, in words, or `""` |
| `orders[].is_gift` | The model never deals with the recipient of a gift order |
| `orders[].expected_delivery_spoken` | Optional. Given only if the buyer asks. |
| `total_cod_amount_spoken` | Total over `orders`, used when a batched call has more than 3 orders |

- Prepare spoken forms in the backend. The model reads `cod_amount_spoken` word for word, so it never misreads `1.250.000` as a decimal number.
- Never include the buyer's phone number, internal order IDs, or the risk score, tier or reasons.
- A batched call (same phone within 15 minutes) lists every order in `orders`.
- Build the object with `json.dumps`, never by string concatenation, so text typed by buyers stays inside JSON strings.

## Call flow

1. The buyer answers, and the call controller opens the Live session.
2. Once the session is set up, the controller sends the start event:

   ```python
   await session.send_client_content(
       turns=types.Content(role="user", parts=[types.Part(text="[CALL_CONNECTED]")]),
       turn_complete=True,
   )
   ```

3. Stream the caller's audio with `send_realtime_input(audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"))` and send the model's audio back to Asterisk. On `server_content.interrupted`, drop the queued audio at once.
4. Run the timers. These are starting values; tune them in E9.2.
   - No buyer speech for 8 s after the model's turn: send `[NO_RESPONSE]` once. Still nothing 8 s later: end the call.
   - At 4 minutes, send `[TIME_UP]`. At 5 minutes, hang up.
5. When `record_call_outcome` arrives, validate it, keep it as the provisional outcome and reply (see the next section). If a `tool_call_cancellation` message lists its id, drop it.
6. After an `ok` reply, wait for the model's closing turn to finish. The server sends `turn_complete` once it estimates playback has ended. Give the queued audio a moment to play out, then close the session.
7. However the call ends, commit exactly one outcome: the last accepted `record_call_outcome`. Without one, commit `NO_ANSWER` if the buyer never spoke and `UNCLEAR` if they did. Store the outcome, the `summary` and both transcripts on the order. An `EDITED` outcome applies the changes and triggers a rescore (E5.4).

| Event | Sent when | What the model does |
|---|---|---|
| `[CALL_CONNECTED]` | The session is ready and the buyer has picked up | Says the opening |
| `[NO_RESPONSE]` | No buyer speech for 8 s | Asks once whether the buyer can hear |
| `[TIME_UP]` | The call reaches 4 minutes | Records an outcome (`UNCLEAR` if undecided) and says goodbye |

Send every event with `send_client_content`, as in step 2.

## The outcome tool

| Code | Label | Set by |
|---|---|---|
| `CONFIRMED` | Xác nhận | Model |
| `EDITED` | Đã sửa | Model |
| `CANCELLED` | Hủy | Model |
| `NOT_ORDERED` | Không đặt | Model |
| `WRONG_PERSON` | Nhầm người | Model |
| `UNCLEAR` | Không rõ | Model, or the backend as a fallback |
| `NO_ANSWER` | Không nghe máy | Backend only |

- `NOT_ORDERED` means whoever holds this phone says nobody there placed the order. It is the call's version of *"Tôi không đặt"*, so the phone gets the 30-day block.
- `WRONG_PERSON` means someone else answered for a buyer who exists, such as a family member on a shared phone. The order needs another attempt or a review.

Validate each call before replying `ok`:

- `outcome` is one of the six model outcomes.
- `EDITED` has at least one change, and other outcomes have none.
- Every `changes[].order_ref` is an order in this call, and `item_variant` or `item_quantity` changes name an item in that order.
- `summary` is not empty.

On 3.8 Live, reply to every call with its exact `id`. Never reply with `{}` or `None`. Include `status`, `retryable` and `message`, where `message` tells the model what to do next:

```python
await session.send_tool_response(
    function_responses=[
        types.FunctionResponse(
            id=call.id,
            name=call.name,
            response={
                "status": "ok",
                "retryable": False,
                "message": "Saved. Say one closing line for CONFIRMED, then stop.",
            },
        )
    ]
)

# A failed validation lets the model fix the call or ask the buyer:
response = {
    "status": "invalid_argument",
    "retryable": True,
    "message": "EDITED needs at least one entry in changes. Add the changes you read back, then call again.",
}
```

If you switch to `gemini-3.8-live-extended-thinking`, change `behavior` to `NON_BLOCKING`, because blocking calls return an error there.

## What the backend decides, not the model

The model only talks and reports the buyer's answer. Keep these rules in code, where they can be tested:

- whether to call at all (expected loss against contact cost);
- contact hours, per-phone limits, batching and attempts;
- the 30-day block and the 7-day trust;
- calling the buyer's phone, never a gift recipient's;
- order state changes, rescoring, and `NO_ANSWER`.

Writing these rules into the prompt would not enforce them.

## Browser audio (E5.2)

With the call controller, the browser joins over WebRTC through Asterisk ([call-controller.md](call-controller.md)), and Asterisk carries the audio. The notes below apply only to a direct browser-to-backend prototype.

- Capture with `getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } })`.
- Resample to 16 kHz mono 16-bit PCM in an AudioWorklet and send 20–40 ms chunks (640–1,280 bytes). Do not buffer more than that.
- Play the model's 24 kHz 16-bit PCM from a queue, and flush the queue on `interrupted`.
- One server message can carry audio, transcripts and flags together, so handle every part of it.
- Test, and record the demo, with headphones. Speaker sound picked up by the microphone makes the model interrupt itself.
- For real phone lines later (E5.5): telephony audio is 8 kHz μ-law. Resample with a stateful resampler, and watch for carrier echo causing false interruptions.

## Limits and cost

- An audio-only session lasts at most 15 minutes without context compression. A connection lasts about 10 minutes and ends with a `go_away` message. If either happens mid-call, end the call and let the fallback outcome apply.
- Gemini API list prices for 3.8 Live (paid tier, per 1M tokens): text in $0.75, audio in $3.00 (about $0.005 a minute), text out $4.50, audio out $12.00 (about $0.018 a minute). Agent Platform prices may differ; check them before quoting.
- Billing is per turn, on everything in the context window, including the instruction (about 2,600 tokens with the example order). Audio is about 25 tokens per second.
- Estimate (ước tính) from those prices, at VND 26,000 per USD:
  - simple confirmation, 1 minute, 5 turns: about $0.04 (VND 1,000);
  - call with edits, 2.5 minutes, 12 turns: about $0.16 (VND 4,000).
- Use these figures as the AI-call contact cost in the decision engine (E4.2) until the spike has real numbers. Log `usage_metadata` for every call so the cost is measured rather than estimated.
- For E1.4, cap demo calls per visitor and per day, on top of the 5-minute call limit.

## E5.1 spike checklist (M1, 9 Oct)

1. Listen first, without code. In Google AI Studio's Live mode, paste the instruction with `{{call_language}}` replaced by `VIETNAMESE` and `{{order_context}}` replaced by the example above. Type `[CALL_CONNECTED]`, then play through each outcome once.
2. Try 3–4 voices and pick one by team vote. Also try asking for a regional accent in the persona; Google recommends naming the output language together with the accent.
3. Accents: three speakers (Northern, Central, Southern) each give five answers that contain an address, a size and a quantity. Check `input_transcription`, and whether the model's read-back got the facts right.
4. Latency from Vietnam to `us-central1`: stream a recorded answer followed by silence, and measure from the last speech chunk sent to the first audio chunk received. Run 20 turns and note p50 and p90.
5. Noise: repeat step 3 for one speaker with TV or street noise in the background.
6. Tool: run 10 scripted calls, 2 for each main outcome. Check that `record_call_outcome` is called once, before the goodbye, with the right outcome and changes.
7. Run the instruction (English rules and lines) once with `call_language` set to `VIETNAMESE` and once against a fully Vietnamese translation, judged on how natural the call sounds.

Proposed go criteria, for the team to agree: the team judges the Vietnamese natural; the facts are right in at least 13 of the 15 accent tests; latency p50 is at most 1.5 s and p90 at most 2.5 s; the tool is right in at least 9 of 10 calls. The no-go fallback from the Scope of Work: demo the AI call in English and send Vietnamese buyers to the confirmation page.

## Privacy

- Demo and test calls use pseudonymised data only: placeholder names such as Nguyễn Văn A, invented addresses and test phone numbers.
- Transcripts contain personal data. Store them with the order and never write them to application logs.
- The Gemini API free tier may use what you send to improve Google products. Use it only with synthetic data.

## Sources

- [Gemini 3.8 Live model card, Gemini API](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live)
- [Gemini 3.8 Live, Agent Platform model page](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-8-live) and [developer guide](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/guides/gemini-3-8-live)
- [Gemini 2.5 Flash Live API, Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/2-5-flash-live-api)
- [Live API overview, Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api)
- [Configure language and voice](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/configure-language-voice)
- Live API best practices: [Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/best-practices), [Gemini API](https://ai.google.dev/gemini-api/docs/live-api/best-practices)
- [Asynchronous function calling](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/asynchronous-function-calling)
- Gemini API guides: [capabilities](https://ai.google.dev/gemini-api/docs/live-guide), [tool use](https://ai.google.dev/gemini-api/docs/live-tools), [session management](https://ai.google.dev/gemini-api/docs/live-session), [pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Google's Live API skill and migration notes](https://github.com/google-gemini/gemini-skills/tree/main/skills/gemini-live-api-dev)
- [google-genai Python SDK](https://github.com/googleapis/python-genai)
- [ADK supported Live models](https://adk.dev/live/models/)
- [Cloud Run WebSockets](https://docs.cloud.google.com/run/docs/triggering/websockets)
- [Gemini 3.8 Live announcement](https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-8-live-gemini-3-8-live-extended-thinking/)
- [Carrier echo with SIP telephony (forum thread)](https://discuss.ai.google.dev/t/gemini-live-api-acoustic-echo-cancellation-needed-for-sip-telephony-deployments/144332)
