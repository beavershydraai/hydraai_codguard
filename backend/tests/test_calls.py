"""E5 backend side of the AI call: creating a call, publishing its job, the controller's
progress and result, and what the result does to the order (docs/call-controller.md)."""

import asyncio
import base64
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api import security
from app.calls import jobs, spoken
from app.calls.pubsub import PubSubPublisher
from app.calls.service import CallService, call_id_for, get_call_service, mask_phone
from app.calls.store import CallNotFound
from app.main import create_app
from app.risk import engine
from app.schemas.enums import CallLanguage, CallTargetKind, OrderStatus
from app.schemas.telephony import CallJob, CallResult, CallStatusUpdate
from tests.test_pipeline import pipe, run, scorer  # noqa: F401 (pytest fixture)
from tests.test_policy import NOW

OVERRIDE = "sip:6001"
CONTROLLER = "codguard-asterisk"


class FakeCallStore:
    def __init__(self):
        self.docs = {}

    def create(self, doc):
        if doc["call_id"] in self.docs:
            return deepcopy(self.docs[doc["call_id"]])
        self.docs[doc["call_id"]] = deepcopy(doc)
        return None

    def get(self, call_id):
        doc = self.docs.get(call_id)
        return deepcopy(doc) if doc else None

    def transact(self, call_id, fn):
        if call_id not in self.docs:
            raise CallNotFound(call_id)
        result = fn(deepcopy(self.docs[call_id]))
        self.docs[call_id] = deepcopy(result)
        return result

    def for_phone(self, phone_hash):
        return [deepcopy(d) for d in self.docs.values() if d.get("phone_hash") == phone_hash]


class FakePublisher:
    def __init__(self, fail=False):
        self.jobs: list[CallJob] = []
        self.fail = fail

    def publish(self, job):
        if self.fail:
            raise ConnectionError("Pub/Sub is unreachable")
        self.jobs.append(job)
        return str(len(self.jobs))


@pytest.fixture
def calls(pipe, monkeypatch):  # noqa: F811
    monkeypatch.setenv("CALL_TARGET_OVERRIDE", OVERRIDE)
    monkeypatch.setattr(engine, "score", scorer("high", "call"))
    return CallService(
        orders=pipe.store, calls=FakeCallStore(), log=pipe.log, publisher=FakePublisher()
    )


def order(calls):
    return calls.orders.get("ord_test")


def result(**fields) -> CallResult:
    base = {
        "status": "completed",
        "outcome": "confirmed",
        "controller_id": CONTROLLER,
        "agent": "gemini_live",
        "language": "vi",
        "input_method": "voice",
        "dial_started_at": NOW + timedelta(seconds=2),
        "answered_at": NOW + timedelta(seconds=6),
        "ended_at": NOW + timedelta(seconds=50),
        "summary_vi": "Buyer confirmed the order.",
        "transcript": [{"speaker": "agent", "text": "Dạ em chào quý khách…", "offset_ms": 300}],
    }
    return CallResult.model_validate(base | fields)


def dialing(calls, call_id, controller=CONTROLLER, status="dialing"):
    return calls.record_status(
        call_id,
        CallStatusUpdate(status=status, at=NOW + timedelta(seconds=2), controller_id=controller),
    )


# --- spoken forms --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("vnd", "vi", "en"),
    [
        (450_000, "bốn trăm năm mươi nghìn đồng", "four hundred fifty thousand dong"),
        (
            1_250_000,
            "một triệu hai trăm năm mươi nghìn đồng",
            "one million two hundred fifty thousand dong",
        ),
        (1_005_000, "một triệu không trăm linh năm nghìn đồng", "one million five thousand dong"),
        (21_000, "hai mươi mốt nghìn đồng", "twenty-one thousand dong"),
        (15_000, "mười lăm nghìn đồng", "fifteen thousand dong"),
        (0, "không đồng", "zero dong"),
    ],
)
def test_amounts_are_read_out_in_words(vnd, vi, en):
    assert spoken.amount(vnd, CallLanguage.VI) == vi
    assert spoken.amount(vnd, CallLanguage.EN) == en


def test_the_order_time_is_read_relative_to_today_in_vietnam_time():
    now = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)  # 16:00 in Vietnam
    assert (
        spoken.placed_at(datetime(2026, 10, 15, 7, tzinfo=UTC), now, CallLanguage.VI) == "chiều nay"
    )
    assert (
        spoken.placed_at(datetime(2026, 10, 14, 12, tzinfo=UTC), now, CallLanguage.VI)
        == "tối hôm qua"
    )
    earlier = datetime(2026, 10, 7, 13, tzinfo=UTC)
    assert spoken.placed_at(earlier, now, CallLanguage.VI) == "tối ngày 7 tháng 10"
    assert spoken.placed_at(earlier, now, CallLanguage.EN) == "on the evening of 7 October"


# --- the job -------------------------------------------------------------------------------


def test_the_job_carries_the_order_in_spoken_form(calls):
    job = jobs.build_job(order(calls), "call_x_1", 1, NOW)
    assert job.target.kind == CallTargetKind.SIP and job.target.address == "6001"
    assert job.env == "demo" and job.agent.value == "gemini_live"
    (call_order,) = job.orders
    assert call_order.order_id == "ord_test"
    assert (
        call_order.cod_amount_vnd == job.total_cod_amount_vnd == jobs.cod_amount_vnd(order(calls))
    )
    assert call_order.cod_amount_spoken.endswith("đồng")
    assert call_order.delivery_address == "Số 12 ngõ 34, phường Láng, Hà Nội"
    assert job.buyer.full_name == "Nguyễn Văn A"


def test_without_the_override_the_call_dials_the_buyers_phone(calls, monkeypatch):
    monkeypatch.delenv("CALL_TARGET_OVERRIDE")
    target = jobs.target_for(order(calls))
    assert target.kind == CallTargetKind.PSTN and target.address == "+84000000001"
    with pytest.raises(jobs.NoTarget):
        jobs.target_for(order(calls) | {"buyer_phone": "12345", "buyer_phone_hash": None})


def test_phones_are_masked():
    assert mask_phone("+84000000001") == "+84******001"


# --- starting a call -----------------------------------------------------------------------


def test_the_shop_starts_a_call_and_the_job_is_published(calls):
    call = calls.start_for_shop("ord_test", "shop_a", "admin@gmail.com", NOW)
    assert call.id == call_id_for("ord_test", 1) and call.status.value == "queued"
    (job,) = calls.publisher.jobs
    assert job.call_id == call.id and job.attempt == 1
    doc = order(calls)
    assert [c["id"] for c in doc["calls"]] == [call.id]
    assert doc["contacts"][0]["call_id"] == call.id
    assert doc["attempts"]["ai_call"] == 1
    assert doc["timeline"][0]["type"] == "contact_started"
    assert "ord_test:ai_call:1" in calls.log.claims


def test_a_second_click_returns_the_running_call(calls):
    first = calls.start_for_shop("ord_test", "shop_a", "admin@gmail.com", NOW)
    again = calls.start_for_shop("ord_test", "shop_a", "admin@gmail.com", NOW)
    assert again.id == first.id and len(calls.publisher.jobs) == 1


def test_two_attempts_then_the_order_is_not_called_again(calls):
    for attempt in (1, 2):
        call = calls.start_for_shop("ord_test", "shop_a", "admin@gmail.com", NOW)
        assert call.attempt == attempt
        dialing(calls, call.id)
        calls.record_result(call.id, result(outcome="no_answer", answered_at=None))
    with pytest.raises(Exception) as blocked:
        calls.start_for_shop("ord_test", "shop_a", "admin@gmail.com", NOW)
    assert blocked.value.problem.block_reasons == ["attempts_exhausted"]


def test_another_shops_order_is_not_found(calls):
    with pytest.raises(Exception) as missing:
        calls.start_for_shop("ord_test", "shop_b", "admin@gmail.com", NOW)
    assert missing.value.problem.status == 404


def test_a_failed_publish_fails_the_call_without_reaching_anyone(calls):
    calls.publisher.fail = True
    call = calls.start_for_shop("ord_test", "shop_a", "admin@gmail.com", NOW)
    assert call.status.value == "failed"
    assert order(calls)["calls"][0]["status"] == "failed"


def test_phone_rules_apply_when_a_real_phone_is_dialled(calls, monkeypatch):
    monkeypatch.delenv("CALL_TARGET_OVERRIDE")
    monkeypatch.setenv("CONTACT_HOURS", "08:00-21:00")
    late = NOW.replace(hour=22)  # NOW is Vietnam time
    with pytest.raises(Exception) as blocked:
        calls.start_for_shop("ord_test", "shop_a", "admin@gmail.com", late)
    assert blocked.value.problem.block_reasons == ["outside_contact_hours"]
    # Another order to the same phone had a call this morning: one AI call per phone per day.
    other = order(calls) | {"order_id": "ord_other", "calls": [], "attempts": {}}
    calls.orders.create(other)
    first = calls.start_for_shop("ord_other", "shop_a", "admin@gmail.com", NOW)
    dialing(calls, first.id)
    with pytest.raises(Exception) as blocked:
        calls.start_for_shop("ord_test", "shop_a", "admin@gmail.com", NOW + timedelta(hours=1))
    assert blocked.value.problem.block_reasons == ["daily_call_limit"]


def test_the_override_skips_the_phone_rules(calls):
    late = NOW.replace(hour=23)
    assert (
        calls.start_for_shop("ord_test", "shop_a", "admin@gmail.com", late).status.value == "queued"
    )


# --- controller progress -------------------------------------------------------------------


def test_dialing_claims_the_call_for_one_controller(calls):
    call = calls.start_for_shop("ord_test", "shop_a", "admin@gmail.com", NOW)
    assert dialing(calls, call.id).status.value == "dialing"
    assert dialing(calls, call.id).status.value == "dialing"  # a retry of the same claim
    with pytest.raises(Exception) as taken:
        dialing(calls, call.id, controller="another-vm")
    assert taken.value.problem.code == "call_not_active"
    assert dialing(calls, call.id, status="in_progress").status.value == "in_progress"
    assert order(calls)["calls"][0]["started_at"] is not None


def test_a_call_nobody_claimed_fails_after_the_grace_period(calls):
    call = calls.start_for_shop("ord_test", "shop_a", "admin@gmail.com", NOW)
    later = NOW + timedelta(minutes=11)
    view = calls.get_for_shop(call.id, "shop_a", later)
    assert view.status.value == "failed"
    assert calls.calls.get(call.id)["failure_reason"] == "controller_error"
    with pytest.raises(Exception) as missing:
        calls.get_for_shop(call.id, "shop_b", later)
    assert missing.value.problem.status == 404


# --- the result ----------------------------------------------------------------------------


def test_a_confirmed_call_clears_the_order_and_keeps_the_transcript_off_the_order(calls):
    asyncio.run(run(_pipe(calls)))
    call = calls.start_for_shop("ord_test", "shop_a", "admin@gmail.com", NOW)
    dialing(calls, call.id)
    view = calls.record_result(call.id, result())
    assert view.outcome.value == "confirmed" and view.duration_seconds == 44
    doc = order(calls)
    assert doc["status"] == OrderStatus.CLEARED_TO_SHIP
    assert doc["confirmation"]["via"] == "call"
    assert doc["contacts"][-1]["result"] == "confirmed"
    assert "transcript" not in doc["calls"][-1]
    assert calls.calls.get(call.id)["transcript"][0]["speaker"] == "agent"
    # The same result again is harmless; a different one is a conflict.
    assert calls.record_result(call.id, result()).outcome.value == "confirmed"
    with pytest.raises(Exception) as conflict:
        calls.record_result(call.id, result(outcome="cancelled"))
    assert conflict.value.problem.status == 409


def test_an_edited_call_changes_the_address(calls):
    asyncio.run(run(_pipe(calls)))
    call = calls.start_for_shop("ord_test", "shop_a", "admin@gmail.com", NOW)
    dialing(calls, call.id)
    change = {
        "order_id": "ord_test",
        "field": "delivery_address",
        "new_value": "Số 15 ngõ 34, Hà Nội",
    }
    calls.record_result(call.id, result(outcome="edited", changes=[change]))
    doc = order(calls)
    assert doc["address"]["raw"] == "Số 15 ngõ 34, Hà Nội"
    assert doc["confirmation"]["via"] == "call"


def test_a_failed_call_leaves_the_order_waiting(calls):
    asyncio.run(run(_pipe(calls)))
    call = calls.start_for_shop("ord_test", "shop_a", "admin@gmail.com", NOW)
    failed = result(
        status="failed", outcome=None, failure_reason="target_unreachable", answered_at=None
    )
    calls.record_result(call.id, failed)
    doc = order(calls)
    assert doc["status"] == OrderStatus.AWAITING_CONFIRMATION
    assert doc["timeline"][0]["type"] == "call_completed"


def _pipe(calls):
    from app.agents.agent import Pipeline

    return Pipeline(store=calls.orders, log=calls.log, now=NOW)


# --- the pipeline places its call for real when calls are configured ------------------------


def test_the_pipeline_places_its_call_through_the_controller(calls):
    from app.agents.agent import Pipeline

    pipeline = Pipeline(store=calls.orders, log=calls.log, now=NOW, calls=calls)
    outcome = asyncio.run(run(pipeline))
    assert outcome["mock"] is False and outcome["call_id"] == call_id_for("ord_test", 1)
    assert calls.publisher.jobs[0].attempt == 1
    assert order(calls)["calls"][0]["id"] == outcome["call_id"]


def test_test_orders_keep_a_simulated_call(calls):
    from app.agents.agent import Pipeline

    calls.orders.docs["ord_test"]["skip_agents"] = True  # sent with a `noagents` intake key
    pipeline = Pipeline(store=calls.orders, log=calls.log, now=NOW, calls=calls)
    outcome = asyncio.run(run(pipeline))
    assert outcome["mock"] is True and calls.publisher.jobs == []


# --- routes --------------------------------------------------------------------------------


@pytest.fixture
def api(calls, monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "admin@gmail.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin12345")
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "test-secret-at-least-32-bytes-long")
    monkeypatch.setenv("ADMIN_SHOP_ID", "shop_a")
    monkeypatch.delenv("INTERNAL_AUTH", raising=False)
    monkeypatch.setenv("INTERNAL_AUDIENCE", "https://backend.example")
    monkeypatch.setenv("CONTROLLER_SERVICE_ACCOUNTS", "vm@example.iam.gserviceaccount.com")
    app = create_app()
    app.dependency_overrides[get_call_service] = lambda: calls
    client = TestClient(app)
    token = client.post(
        "/api/v1/auth/login", json={"username": "admin@gmail.com", "password": "admin12345"}
    ).json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_the_shop_app_starts_and_polls_a_call(api):
    client, headers = api
    response = client.post("/api/v1/orders/ord_test/calls", headers=headers)
    assert response.status_code == 202, response.text
    call_id = response.json()["id"]
    assert client.get(f"/api/v1/calls/{call_id}", headers=headers).json()["status"] == "queued"
    assert client.post("/api/v1/orders/ord_test/calls").status_code == 401


def test_the_controller_needs_an_allowed_service_account(api, calls, monkeypatch):
    client, headers = api
    call_id = client.post("/api/v1/orders/ord_test/calls", headers=headers).json()["id"]
    body = {"status": "dialing", "at": NOW.isoformat(), "controller_id": CONTROLLER}
    path = f"/api/v1/internal/calls/{call_id}/status"

    def verify(token, request, audience):
        assert audience == "https://backend.example"
        return {"email": token, "email_verified": True}

    monkeypatch.setattr(security.id_token, "verify_oauth2_token", verify)
    stranger = {"Authorization": "Bearer someone@example.com"}
    assert client.post(path, json=body, headers=stranger).status_code == 401
    vm = {"Authorization": "Bearer vm@example.iam.gserviceaccount.com"}
    response = client.post(path, json=body, headers=vm)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "dialing"
    assert client.post(path, json=body | {"controller_id": "other"}, headers=vm).status_code == 409


def test_the_publisher_sends_the_job_with_its_attributes(calls):
    sent = {}

    class Session:
        def post(self, url, json, timeout):
            sent.update(url=url, body=json)

            class Response:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"messageIds": ["42"]}

            return Response()

    publisher = PubSubPublisher("projects/p/topics/call-jobs")
    publisher.__dict__["_session"] = Session()
    job = jobs.build_job(order(calls), "call_x_1", 1, NOW)
    assert publisher.publish(job) == "42"
    assert sent["url"] == "https://pubsub.googleapis.com/v1/projects/p/topics/call-jobs:publish"
    (message,) = sent["body"]["messages"]
    assert message["attributes"] == {
        "env": "demo",
        "call_id": "call_x_1",
        "target_kind": "sip",
        "agent": "gemini_live",
    }
    assert CallJob.model_validate_json(base64.b64decode(message["data"])).call_id == "call_x_1"
