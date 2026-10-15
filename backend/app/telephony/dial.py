"""Dev tool: have Asterisk call a softphone or a phone and talk to it with the gemini_live agent,
on a built-in sample order. Prints the CallResult as JSON.

    python -m app.telephony.dial 6001 [--language en]       softphone on the Mesh (sip)
    python -m app.telephony.dial +84XXXXXXXXX                phone, via the Twilio trunk (pstn)

An address starting with `+` is a phone; it needs infra/asterisk/trunk-setup.sh on the VM.

Needs ARI_URL, ARI_USER, ARI_PASSWORD and the Gemini Live variables (GOOGLE_CLOUD_PROJECT,
GEMINI_LIVE_LOCATION, GEMINI_LIVE_MODEL). It registers its own ARI app, `codguard-dial`, so it
can run next to the controller without taking its events.
"""

import argparse
import asyncio
import logging
import os
import re
import sys
from datetime import UTC, datetime

import websockets

from app.schemas.enums import CallLanguage, CallTargetKind
from app.schemas.telephony import CallJob, CallResult
from app.telephony.ari import AriClient
from app.telephony.call import CallRunner

APP = "codguard-dial"
E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")

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
    parser.add_argument("address", help="softphone extension (sip), or a phone in E.164 (pstn)")
    parser.add_argument("--language", choices=[lang.value for lang in CallLanguage], default="vi")
    parser.add_argument(
        "--kind",
        choices=[kind.value for kind in CallTargetKind],
        help="default: pstn when the address starts with +, otherwise sip",
    )
    args = parser.parse_args()
    kind = CallTargetKind(args.kind or ("pstn" if args.address.startswith("+") else "sip"))
    if kind == CallTargetKind.PSTN and not E164.match(args.address):
        parser.error("a phone number must be in E.164 form, like +84XXXXXXXXX")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its request lines carry the number
    job = sample_job(args.address, CallLanguage(args.language), kind)
    try:
        result = asyncio.run(dial(job))
    except (OSError, websockets.exceptions.InvalidStatus) as exc:
        sys.exit(f"Cannot reach ARI at {os.environ['ARI_URL']}: {exc}")
    # Sample data only, so the transcript may go to the terminal (not to a log).
    sys.stdout.write(result.model_dump_json(indent=2) + "\n")


if __name__ == "__main__":
    main()
