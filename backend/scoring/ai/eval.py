"""Run E3 prompts against synthetic answer keys; human review remains required.

Live mode uses Gemini. ``--offline`` parses explicitly recorded structured
responses through the same gateway and checks; it measures regression behavior,
not Gemini quality or the E3.3 human acceptance criterion.
"""

import argparse
import asyncio
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Address
from app.schemas.enums import RiskTier
from app.schemas.orders import OrderCreate
from app.schemas.scoring import Signal
from scoring.ai.address import AddressParts, extract_address
from scoring.ai.client import GeminiClient
from scoring.ai.conversation import ConversationParts, extract_conversation
from scoring.ai.reason_check import CheckResult, check_reasons
from scoring.ai.reasons import generate_reasons

DEFAULT_INPUT = Path(__file__).parents[2] / "tests" / "data" / "e3_eval_orders.jsonl"
ADDRESS_FLAGS = (
    "address_missing_house_number",
    "address_missing_ward",
    "address_vague",
    "address_legacy_admin_names",
)


class AddressExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completeness_min: float | None = Field(default=None, ge=0, le=1)
    completeness_max: float | None = Field(default=None, ge=0, le=1)
    flags: dict[str, bool]
    normalized: Address | None = None
    admin_unresolved: bool | None = None


class ReasonExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_signal_keys: list[str]


class Expectations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: AddressExpectation
    conversation: dict[str, bool] | None
    reasons: ReasonExpectation


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str
    order: OrderCreate
    signals: list[Signal]
    expected: Expectations
    tier: RiskTier | None = None
    facts: dict[str, dict[str, str | int | float]] = Field(default_factory=dict)
    recorded_address: AddressParts | None = None
    recorded_conversation: ConversationParts | None = None
    recorded_reasons: list[dict[str, Any]] = Field(default_factory=list)
    recorded_retry_reasons: list[dict[str, Any]] | None = None


def load_cases(path: Path) -> list[EvaluationCase]:
    """Validate the orders and answer keys before any paid requests are sent."""
    cases = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = EvaluationCase.model_validate_json(line)
        except ValueError as exc:
            raise ValueError(f"Invalid evaluation case on line {number}") from exc
        if set(case.expected.address.flags) != set(ADDRESS_FLAGS):
            raise ValueError(f"Case {case.id} must define all four address flags")
        positives = {signal.key for signal in case.signals if signal.contribution > 0}
        if not set(case.expected.reasons.allowed_signal_keys) <= positives:
            raise ValueError(f"Case {case.id} allows reason keys absent from positive signals")
        cases.append(case)
    if not cases:
        raise ValueError("Evaluation dataset is empty")
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("Evaluation case IDs must be unique")
    return cases


def _recorded_transport(case: EvaluationCase):
    async def transport(model, instruction, payload, response_schema):
        if response_schema is AddressParts:
            if case.recorded_address is None:
                raise ValueError(f"Case {case.id} has no recorded address extraction")
            return case.recorded_address.model_dump(mode="json")
        if response_schema is ConversationParts:
            if case.recorded_conversation is None:
                raise ValueError(f"Case {case.id} has no recorded conversation extraction")
            return case.recorded_conversation.model_dump(mode="json")
        if "reasons" in response_schema.model_fields:
            candidates = case.recorded_reasons
            if payload.get("rejection_notes") and case.recorded_retry_reasons is not None:
                candidates = case.recorded_retry_reasons
            return {"reasons": candidates}
        raise ValueError("Unknown recorded E3 response schema")

    return transport


def _address_report(actual, expected: AddressExpectation) -> dict:
    values = {signal.key: signal.value for signal in actual.signals} if actual else {}
    completeness = values.get("address_completeness")
    minimum = expected.completeness_min
    maximum = expected.completeness_max
    completeness_passed = completeness is not None and (
        (minimum is None or completeness >= minimum - 1e-9)
        and (maximum is None or completeness <= maximum + 1e-9)
    )
    mismatches = [key for key in ADDRESS_FLAGS if values.get(key) != expected.flags[key]]
    normalized_passed = None
    if expected.normalized is not None:
        normalized_passed = actual is not None and actual.normalized == expected.normalized
    return {
        "available": actual is not None,
        "completeness": completeness,
        "completeness_passed": completeness_passed,
        "flags": {key: values.get(key) for key in ADDRESS_FLAGS},
        "flag_mismatches": mismatches,
        "normalized_passed": normalized_passed,
        "admin_unresolved": actual.admin_unresolved if actual else None,
        "admin_resolution_passed": (
            None
            if expected.admin_unresolved is None
            else actual is not None and actual.admin_unresolved == expected.admin_unresolved
        ),
    }


async def evaluate(cases: list[EvaluationCase], *, offline: bool = False) -> dict:
    """Evaluate extraction and final reason checks, preserving rejection telemetry."""
    if not offline:
        if not os.getenv("GEMINI_MODEL", "").strip():
            raise ValueError("Live evaluation requires GEMINI_MODEL")
        if not os.getenv("GOOGLE_CLOUD_PROJECT", "").strip():
            raise ValueError("Live evaluation requires GOOGLE_CLOUD_PROJECT and ADC credentials")
    results = []
    total_stats: Counter[str] = Counter()
    total_drops: Counter[str] = Counter()
    total_calls = 0
    final_failures = 0
    disallowed_count = 0
    # Evaluation disables result caching so every case exercises the prompts.
    live_client = GeminiClient(cache_size=0) if not offline else None
    try:
        for case in cases:
            client = live_client or GeminiClient(
                model="recorded-evaluation",
                transport=_recorded_transport(case),
                cache_size=0,
            )
            drops: Counter[str] = Counter()
            notes: list[str] = []

            def on_check(result: CheckResult, drops=drops, notes=notes) -> None:
                drops.update(result.dropped)
                notes.extend(result.rejection_notes)

            try:
                address = await extract_address(client, case.order.address)
                conversation = await extract_conversation(client, case.order)
                reasons = await generate_reasons(
                    client,
                    case.signals,
                    tier=case.tier,
                    facts=case.facts,
                    on_check=on_check,
                )
                final_check = check_reasons(reasons, case.signals, tier=case.tier, facts=case.facts)
                allowed = set(case.expected.reasons.allowed_signal_keys)
                disallowed = sorted(
                    {key for r in reasons for key in r.signal_keys if key not in allowed}
                )
                check_passed = len(final_check.reasons) == len(reasons) and not final_check.dropped
                final_failures += int(not check_passed)
                disallowed_count += len(disallowed)
                chat_values = {s.key: s.value for s in conversation} if conversation else None
                expected_chat = case.expected.conversation
                chat_mismatches = (
                    []
                    if expected_chat is None and chat_values is None
                    else [
                        key
                        for key, value in (expected_chat or {}).items()
                        if (chat_values or {}).get(key) != value
                    ]
                )
                results.append(
                    {
                        "id": case.id,
                        "type": case.type,
                        "address": _address_report(address, case.expected.address),
                        "conversation": {
                            "expected_present": expected_chat is not None,
                            "actual_present": chat_values is not None,
                            "flags": chat_values,
                            "flag_mismatches": chat_mismatches,
                        },
                        "reasons": {
                            "written": [reason.model_dump(mode="json") for reason in reasons],
                            "allowed_signal_keys": sorted(allowed),
                            "disallowed_signal_keys": disallowed,
                            "dropped": dict(drops),
                            "rejection_notes": notes,
                            "check_passed": check_passed,
                        },
                    }
                )
                total_drops.update(drops)
            finally:
                if offline:
                    total_stats.update(client.stats)
                    total_calls += client.calls_made
                    await client.aclose()
    finally:
        if live_client is not None:
            total_stats.update(live_client.stats)
            total_calls += live_client.calls_made
            await live_client.aclose()
    checked_flags = len(results) * len(ADDRESS_FLAGS)
    incorrect_flags = sum(len(case["address"]["flag_mismatches"]) for case in results)
    chat_checked = sum(
        len(case.expected.conversation) for case in cases if case.expected.conversation is not None
    )
    chat_incorrect = sum(len(case["conversation"]["flag_mismatches"]) for case in results)
    unavailable = sum(not case["address"]["available"] for case in results)
    unavailable += sum(
        case["conversation"]["expected_present"] and not case["conversation"]["actual_present"]
        for case in results
    )
    errors = sum(
        total_stats[key]
        for key in (
            "unavailable",
            "timeout",
            "error",
            "call_cap",
            "empty_response",
            "invalid_exhausted",
        )
    )
    status = "checks_passed" if not (final_failures or disallowed_count) else "check_failed"
    if unavailable or errors:
        status = "recorded_response_error" if offline else "incomplete_live_run"
    return {
        "mode": "offline" if offline else "live",
        "status": status,
        "case_count": len(results),
        "review_required": True,
        "acceptance_status": (
            "pending_live_and_human_review"
            if offline
            else "pending_human_review"
            if status == "checks_passed"
            else "pending_successful_live_run"
        ),
        "note": (
            "Recorded responses test parsing, deterministic features and reason checks. "
            "A successful live run and independent human review of all final reasons "
            "are required for E3.3 acceptance."
            if offline
            else "Machine checks cannot establish 0 invented reasons; independent human review "
            "of every final reason is required."
        ),
        "gemini_calls": 0 if offline else total_calls,
        "recorded_responses": total_calls if offline else 0,
        "gateway_events": dict(total_stats),
        "address": {
            "flags_checked": checked_flags,
            "flag_accuracy": (checked_flags - incorrect_flags) / checked_flags
            if checked_flags
            else None,
            "completeness_cases_passed": sum(
                case["address"]["completeness_passed"] for case in results
            ),
        },
        "conversation": {
            "flags_checked": chat_checked,
            "flag_accuracy": (chat_checked - chat_incorrect) / chat_checked
            if chat_checked
            else None,
        },
        "reasons": {
            "written_count": sum(len(case["reasons"]["written"]) for case in results),
            "dropped": dict(total_drops),
            "dropped_count": sum(total_drops.values()),
            "machine_check_failures": final_failures,
            "disallowed_signal_keys": disallowed_count,
        },
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--offline", action="store_true", help="Use recorded responses; no Gemini calls"
    )
    args = parser.parse_args()
    try:
        report = asyncio.run(evaluate(load_cases(args.input), offline=args.offline))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(
            f"{report['mode']} evaluation: {report['case_count']} cases; "
            f"status={report['status']}; human review required; report={args.output}"
        )
    else:
        print(text, end="")
    return 0 if report["status"] == "checks_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
