"""Dev tool: have Asterisk call a softphone and talk to it with the gemini_live agent, on a
built-in sample order. Prints the CallResult as JSON.

    python -m app.telephony.dial 6001 [--language en]

Needs ARI_URL, ARI_USER, ARI_PASSWORD and the Gemini Live variables (GOOGLE_CLOUD_PROJECT,
GEMINI_LIVE_LOCATION, GEMINI_LIVE_MODEL). It registers its own ARI app, `codguard-dial`, so it
can run next to the controller without taking its events.
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import UTC, datetime

import websockets

from app.schemas.enums import CallLanguage, CallTargetKind
from app.schemas.telephony import CallJob, CallResult
from app.telephony.ari import AriClient
from app.telephony.call import CallRunner

APP = "codguard-dial"

# English spoken forms for the sample order; the Vietnamese ones come from the contract example.
ENGLISH_SPOKEN = {
    "placed_at_spoken": "on the evening of October 7",
    "cod_amount_spoken": "four hundred and fifty thousand dong",
    "expected_delivery_spoken": "2 to 3 days after it ships",
}


def sample_job(
    address: str, language: CallLanguage, kind: CallTargetKind = CallTargetKind.SIP
) -> CallJob:
    example = CallJob.model_config["json_schema_extra"]["examples"][0]  # type: ignore[index]
    now = datetime.now(UTC)
    data = {
        **example,
        "call_id": f"dev-{now:%Y%m%d-%H%M%S}",
        "env": "dev-cli",
        "target": {"kind": kind, "address": address},
        "agent": "gemini_live",
        "language": language,
        "created_at": now.isoformat(),
    }
    if language == CallLanguage.EN:
        data["orders"] = [{**order, **ENGLISH_SPOKEN} for order in example["orders"]]
        data["total_cod_amount_spoken"] = ENGLISH_SPOKEN["cod_amount_spoken"]
    return CallJob.model_validate(data)


async def dial(job: CallJob) -> CallResult:
    ari = AriClient(os.environ["ARI_URL"], os.environ["ARI_USER"], os.environ["ARI_PASSWORD"], APP)
    runner = CallRunner(ari, job, controller_id=os.environ.get("CONTROLLER_ID", "dev-dial"))
    try:
        async with ari.event_stream() as events:

            async def route() -> None:
                async for event in events:
                    if runner.wants(event):
                        runner.events.put_nowait(event)

            router = asyncio.create_task(route())
            try:
                return await runner.run()
            finally:
                router.cancel()
    finally:
        await ari.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("address", help="softphone extension (sip), for example 6001")
    parser.add_argument("--language", choices=[lang.value for lang in CallLanguage], default="vi")
    parser.add_argument("--kind", choices=[kind.value for kind in CallTargetKind], default="sip")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    job = sample_job(args.address, CallLanguage(args.language), CallTargetKind(args.kind))
    try:
        result = asyncio.run(dial(job))
    except (OSError, websockets.exceptions.InvalidStatus) as exc:
        sys.exit(f"Cannot reach ARI at {os.environ['ARI_URL']}: {exc}")
    # Sample data only, so the transcript may go to the terminal.
    sys.stdout.write(result.model_dump_json(indent=2) + "\n")


if __name__ == "__main__":
    main()
