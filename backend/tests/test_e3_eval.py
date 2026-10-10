"""The recorded evaluation exercises parsing and checks without claiming live acceptance."""

import asyncio
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

from app.schemas.orders import OrderCreate
from app.schemas.scoring import Signal

DATASET = Path(__file__).parent / "data" / "e3_eval_orders.jsonl"


def read_cases():
    return [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]


def test_evaluation_dataset_validates_and_covers_thirty_synthetic_orders():
    cases = read_cases()
    assert len(cases) == 30
    assert len({case["id"] for case in cases}) == 30
    assert Counter(case["type"] for case in cases) == {
        "address_complete": 4,
        "address_legacy_names": 3,
        "address_missing_house_number": 3,
        "address_missing_ward_or_province": 3,
        "address_vague": 3,
        "address_messy_text": 3,
        "chat_asked_details": 3,
        "chat_rushed": 3,
        "chat_name_mismatch": 2,
        "gift_order": 2,
        "no_risk_signal": 1,
    }
    groups = set()
    for case in cases:
        order = OrderCreate.model_validate(case["order"])
        assert order.buyer_name.startswith("Khách Mẫu")
        assert order.buyer_phone.startswith("+84000")
        if order.recipient_name:
            assert order.recipient_name.startswith("Người Nhận Mẫu")
        for raw in case["signals"]:
            signal = Signal.model_validate(raw)
            groups.add(signal.group.value)
        assert set(case["expected"]["address"]["flags"]) == {
            "address_missing_house_number",
            "address_missing_ward",
            "address_vague",
            "address_legacy_admin_names",
        }
    assert groups >= {"phone_history", "address_quality", "order_behavior", "velocity", "context"}


def test_offline_evaluation_runs_recorded_parsing_and_reports_review_pending():
    from scoring.ai.eval import evaluate, load_cases

    report = asyncio.run(evaluate(load_cases(DATASET), offline=True))
    assert report["mode"] == "offline"
    assert report["gemini_calls"] == 0
    assert report["recorded_responses"] > 0
    assert report["case_count"] == 30
    assert report["address"]["flags_checked"] == 120
    assert report["address"]["flag_accuracy"] == 1.0
    assert report["reasons"]["disallowed_signal_keys"] == 0
    assert report["reasons"]["dropped_count"] > 0
    assert report["review_required"] is True
    assert report["acceptance_status"] == "pending_live_and_human_review"
    assert len(report["cases"]) == 30
    empty = next(case for case in report["cases"] if case["id"] == "e3-030")
    assert empty["reasons"]["written"] == []
    assert all(case["reasons"]["check_passed"] for case in report["cases"])


def test_offline_evaluation_compares_recorded_output_to_independent_answer_key():
    from scoring.ai.eval import evaluate, load_cases

    cases = load_cases(DATASET)[:1]
    cases[0].recorded_address.house_number = None
    report = asyncio.run(evaluate(cases, offline=True))
    assert report["address"]["flag_accuracy"] == 0.75
    assert report["cases"][0]["address"]["flag_mismatches"] == ["address_missing_house_number"]
    assert report["cases"][0]["address"]["completeness_passed"] is False


def test_offline_cli_writes_report_without_gemini_credentials(tmp_path):
    output = tmp_path / "report.json"
    env = os.environ.copy()
    for key in ("GEMINI_MODEL", "GOOGLE_CLOUD_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS"):
        env.pop(key, None)
    result = subprocess.run(
        [sys.executable, "-m", "scoring.ai.eval", "--offline", "--output", str(output)],
        cwd=Path(__file__).parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text())
    assert report["mode"] == "offline"
    assert report["case_count"] == 30
    assert report["review_required"] is True


def test_live_cli_requires_config_instead_of_reporting_offline_fallback(tmp_path):
    output = tmp_path / "report.json"
    env = os.environ.copy()
    env.pop("GEMINI_MODEL", None)
    result = subprocess.run(
        [sys.executable, "-m", "scoring.ai.eval", "--output", str(output)],
        cwd=Path(__file__).parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "GEMINI_MODEL" in result.stderr
    assert not output.exists()


def test_live_timeout_reports_pending_live_run_even_when_templates_pass(monkeypatch):
    from scoring.ai.client import GeminiClient
    from scoring.ai.eval import evaluate, load_cases

    async def timeout_request(self, instruction, payload, response_schema):
        raise TimeoutError

    monkeypatch.setenv("GEMINI_MODEL", "synthetic-evaluation-model")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "synthetic-evaluation-project")
    monkeypatch.setattr(GeminiClient, "_request", timeout_request)
    report = asyncio.run(evaluate(load_cases(DATASET)[:1]))
    assert report["status"] == "incomplete_live_run"
    assert report["gateway_events"]["timeout"] == 2
    assert report["acceptance_status"] == "pending_successful_live_run"
    assert report["reasons"]["machine_check_failures"] == 0
    assert report["review_required"] is True


def test_exhausted_reason_schema_retries_cannot_count_as_live_prompt_success(monkeypatch):
    from scoring.ai.address import AddressParts
    from scoring.ai.client import GeminiClient
    from scoring.ai.eval import evaluate, load_cases

    cases = load_cases(DATASET)[:1]

    async def malformed_reasons(self, instruction, payload, response_schema):
        if response_schema is AddressParts:
            return cases[0].recorded_address.model_dump(mode="json")
        return {"reasons": [{"text_vi": "Địa chỉ thiếu số nhà.", "signal_keys": []}]}

    monkeypatch.setenv("GEMINI_MODEL", "synthetic-evaluation-model")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "synthetic-evaluation-project")
    monkeypatch.setattr(GeminiClient, "_request", malformed_reasons)
    report = asyncio.run(evaluate(cases))
    assert report["gateway_events"]["invalid_response"] == 2
    assert report["status"] == "incomplete_live_run"
    assert report["acceptance_status"] == "pending_successful_live_run"
    assert report["reasons"]["written_count"] > 0  # Safe templates still serve scoring.


def test_recovered_reason_schema_retry_is_a_complete_live_run(monkeypatch):
    from scoring.ai.address import AddressParts
    from scoring.ai.client import GeminiClient
    from scoring.ai.eval import evaluate, load_cases

    cases = load_cases(DATASET)[:1]
    attempts = 0

    async def recovered_reasons(self, instruction, payload, response_schema):
        nonlocal attempts
        if response_schema is AddressParts:
            return cases[0].recorded_address.model_dump(mode="json")
        attempts += 1
        if attempts == 1:
            return {"reasons": [{"text_vi": "Địa chỉ thiếu số nhà.", "signal_keys": []}]}
        return {"reasons": cases[0].recorded_reasons}

    monkeypatch.setenv("GEMINI_MODEL", "synthetic-evaluation-model")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "synthetic-evaluation-project")
    monkeypatch.setattr(GeminiClient, "_request", recovered_reasons)
    report = asyncio.run(evaluate(cases))
    assert report["gateway_events"]["invalid_response"] == 1
    assert report["status"] == "checks_passed"
    assert report["acceptance_status"] == "pending_human_review"
