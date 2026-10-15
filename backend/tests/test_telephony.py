"""Contract between the backend and the call controller (docs/call-controller.md)."""

import copy

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from app.schemas.telephony import CallJob, CallResult

client = TestClient(create_app())
COMPLETED, FAILED = CallResult.model_config["json_schema_extra"]["examples"]
JOB = CallJob.model_config["json_schema_extra"]["examples"][0]


@pytest.mark.parametrize(
    ("path", "body", "operation"),
    [
        (
            "/api/v1/internal/calls/call_01/status",
            {"status": "dialing", "at": "2026-10-13T10:15:08+07:00", "controller_id": "vm"},
            "report_call_status",
        ),
        ("/api/v1/internal/calls/call_01/result", COMPLETED, "record_call_result"),
    ],
)
def test_internal_endpoints_need_a_controller_token(
    path: str, body: dict, operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("INTERNAL_AUTH", raising=False)
    monkeypatch.setenv("INTERNAL_AUDIENCE", "https://backend.example")
    response = client.post(path, json=body, headers={"Authorization": "Bearer test"})
    assert response.status_code == 401
    assert client.post(path, json=body).status_code == 401


@pytest.mark.parametrize(
    ("path", "body", "operation"),
    [
        (
            "/api/v1/internal/calls/call_01/status",
            {"status": "dialing", "at": "2026-10-13T10:15:08+07:00", "controller_id": "vm"},
            "report_call_status",
        ),
        ("/api/v1/internal/calls/call_01/result", COMPLETED, "record_call_result"),
    ],
)
def test_internal_endpoints_answer_501_until_calls_are_configured(
    path: str, body: dict, operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERNAL_AUTH", "off")
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("CALL_JOBS_TOPIC", raising=False)
    response = client.post(path, json=body)
    assert response.status_code == 501
    assert operation in response.json()["detail"]


def test_internal_auth_off_is_ignored_on_cloud_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_AUTH", "off")
    monkeypatch.setenv("K_SERVICE", "codguard-api")
    path = "/api/v1/internal/calls/call_01/result"
    assert client.post(path, json=COMPLETED).status_code == 401


def _result(**changes: object) -> dict:
    result = copy.deepcopy(COMPLETED)
    result.update(changes)
    return result


@pytest.mark.parametrize(
    "result",
    [
        _result(outcome=None),
        _result(failure_reason="agent_error"),
        _result(status="failed", failure_reason="agent_error"),
        _result(outcome="edited", changes=[]),
        _result(outcome="confirmed", changes=[], answered_at=None),
        _result(dtmf="12a"),
        _result(recording_uri="https://example.com/call.wav"),
    ],
    ids=[
        "completed-without-outcome",
        "completed-with-failure",
        "failed-with-outcome",
        "edited-without-changes",
        "unanswered-but-confirmed",
        "bad-dtmf",
        "recording-not-in-gcs",
    ],
)
def test_inconsistent_results_are_rejected(result: dict) -> None:
    with pytest.raises(ValidationError):
        CallResult.model_validate(result)


def test_unanswered_call_completes_as_no_answer() -> None:
    result = _result(
        outcome="no_answer",
        answered_at=None,
        input_method="none",
        changes=[],
        transcript=[],
        recording_uri=None,
    )
    assert CallResult.model_validate(result).outcome == "no_answer"


def test_job_env_selects_a_controller() -> None:
    CallJob.model_validate({**JOB, "env": "dev-the"})
    with pytest.raises(ValidationError):
        CallJob.model_validate({**JOB, "env": "prod"})


def test_contract_documents_the_job_and_the_auth() -> None:
    spec = create_app().openapi()
    job = spec["webhooks"]["call-job"]["post"]
    assert job["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CallJob"
    }
    assert "googleIdToken" in spec["components"]["securitySchemes"]
    for path, item in spec["paths"].items():
        if path.startswith("/api/v1/internal/"):
            assert item["post"]["security"] == [{"googleIdToken": []}], path
