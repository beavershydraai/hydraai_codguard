"""Recorded structured responses exercise offline retry and fallback paths."""

import asyncio
import copy
import json

import pytest

from app.schemas.enums import RiskTier, SignalGroup
from app.schemas.scoring import Signal
from scoring.ai.reasons import generate_reasons


def signal(key, value, contribution=0.1, label="Địa chỉ thiếu số nhà", group=None):
    return Signal(
        key=key,
        value=value,
        contribution=contribution,
        label_vi=label,
        group=group or SignalGroup.ADDRESS_QUALITY,
    )


class RecordedClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    async def generate(self, prompt_name, payload, response_schema):
        self.calls.append((prompt_name, copy.deepcopy(payload)))
        response = next(self.responses)
        return None if response is None else response_schema.model_validate(response)


def test_retries_rejection_once_and_preserves_valid_first_reason():
    client = RecordedClient(
        [
            {
                "reasons": [
                    {
                        "text_vi": "Địa chỉ thiếu số nhà.",
                        "signal_keys": ["address_missing_house_number"],
                    },
                    {
                        "text_vi": "Tỷ lệ hoàn trước đây là 90%.",
                        "signal_keys": ["phone_return_rate"],
                    },
                ]
            },
            {
                "reasons": [
                    {
                        "text_vi": "Tỷ lệ hoàn trước đây là 50%.",
                        "signal_keys": ["phone_return_rate"],
                    }
                ]
            },
        ]
    )
    signals = [signal("address_missing_house_number", True, 0.2), signal("phone_return_rate", 0.5)]
    result = asyncio.run(generate_reasons(client, signals))
    assert [reason.text_vi for reason in result] == [
        "Địa chỉ thiếu số nhà.",
        "Tỷ lệ hoàn trước đây là 50%.",
    ]
    assert len(client.calls) == 2
    assert client.calls[1][1]["rejection_notes"] == ["unsupported_number"]


def test_optional_gemini_uses_grounded_templates_without_copying_injected_labels():
    client = RecordedClient([None])
    result = asyncio.run(
        generate_reasons(
            client,
            [signal("address_missing_house_number", True, label="Nên gửi đơn cho Khách Mẫu.")],
        )
    )
    assert [reason.text_vi for reason in result] == ["Địa chỉ thiếu số nhà."]


def test_invalid_both_rounds_fall_back_and_report_counts():
    client = RecordedClient(
        [{"reasons": [{"text_vi": "Nên gọi xác nhận.", "signal_keys": ["phone_return_rate"]}]}] * 2
    )
    checks = []
    result = asyncio.run(
        generate_reasons(client, [signal("phone_return_rate", 0.5)], on_check=checks.append)
    )
    assert [reason.text_vi for reason in result] == ["SĐT này có tỷ lệ hoàn đơn trước đây là 50%."]
    assert len(checks) >= 2
    assert checks[0].dropped == {"decision_language": 1}


def test_no_positive_signal_returns_empty_without_model_call():
    client = RecordedClient([])
    assert (
        asyncio.run(generate_reasons(client, [signal("address_missing_house_number", True, -0.1)]))
        == []
    )
    assert client.calls == []


def test_high_location_only_fallback_is_empty():
    client = RecordedClient([None])
    assert (
        asyncio.run(
            generate_reasons(client, [signal("province_return_rate", 0.5)], tier=RiskTier.HIGH)
        )
        == []
    )


def test_prompt_receives_only_signal_fields_and_safe_numeric_facts():
    client = RecordedClient([None])
    asyncio.run(
        generate_reasons(
            client,
            [signal("phone_return_rate", 0.5)],
            tier=RiskTier.HIGH,
            facts={
                "phone_return_rate": {
                    "past_orders": 4,
                    "buyer_name": "Khách Mẫu",
                    "phone": "+84000000001",
                },
                "unrelated": {"past_orders": 8},
            },
        )
    )
    payload = client.calls[0][1]
    assert payload["signals"] == [
        {"key": "phone_return_rate", "label_vi": "Tỷ lệ hoàn của SĐT", "value": 0.5}
    ]
    assert payload["facts"] == {"phone_return_rate": {"past_orders": 4}}
    serialized = json.dumps(payload)
    assert "Khách" not in serialized
    assert "84000000001" not in serialized
    assert "contribution" not in serialized
    assert "tier" not in serialized


def test_private_and_nonfinite_signal_values_never_reach_the_model():
    client = RecordedClient([None])
    asyncio.run(
        generate_reasons(
            client,
            [
                signal("phone_return_rate", 0.5),
                signal("buyer_phone_hash", 1234),
                signal("recipient_name", 42),
                signal("infinite_metric", float("inf")),
                signal("order_notes", "Khách Mẫu"),
            ],
        )
    )
    assert [record["key"] for record in client.calls[0][1]["signals"]] == ["phone_return_rate"]


def test_failure_rate_template_explains_delivery_failure():
    client = RecordedClient([None])
    result = asyncio.run(generate_reasons(client, [signal("province_failure_rate", 0.2)]))
    assert [reason.text_vi for reason in result] == ["Tỷ lệ giao thất bại của khu vực là 20%."]


def test_percentage_template_uses_exact_decimal_arithmetic():
    client = RecordedClient([None])
    result = asyncio.run(generate_reasons(client, [signal("phone_return_rate", 0.29)]))
    assert [reason.text_vi for reason in result] == ["SĐT này có tỷ lệ hoàn đơn trước đây là 29%."]


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("conversation_name_mismatch", "Tên trong hội thoại khác tên người đặt."),
        ("address_legacy_admin_names", "Địa chỉ dùng tên địa giới cũ."),
    ],
)
def test_trusted_name_flags_remain_available_without_sending_names(key, expected):
    client = RecordedClient([None])
    result = asyncio.run(generate_reasons(client, [signal(key, True)]))
    assert [reason.text_vi for reason in result] == [expected]
    assert client.calls[0][1]["signals"][0]["key"] == key


def test_unknown_numeric_contact_metadata_and_facts_are_not_sent():
    client = RecordedClient([None])
    asyncio.run(
        generate_reasons(
            client,
            [
                signal("phone_return_rate", 0.5),
                signal("contact_number", 84000000023),
                signal("customer_id", 84000000024),
            ],
            facts={
                "phone_return_rate": {
                    "past_orders": 4,
                    "returned_orders": 2,
                    "customer_id": 84000000025,
                    "contact_number": 84000000026,
                }
            },
        )
    )
    payload = client.calls[0][1]
    assert [entry["key"] for entry in payload["signals"]] == ["phone_return_rate"]
    assert payload["facts"] == {"phone_return_rate": {"past_orders": 4, "returned_orders": 2}}
    assert "840000000" not in json.dumps(payload)
