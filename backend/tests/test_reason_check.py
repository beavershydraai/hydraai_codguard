"""Offline grounding checks using synthetic signal records."""

import pytest

from app.schemas.enums import RiskTier, SignalGroup
from app.schemas.scoring import Reason, Signal
from scoring.ai.reason_check import check_reasons


def signal(key="phone_return_rate", value=0.5, contribution=0.18, group=None):
    return Signal(
        key=key,
        group=group or SignalGroup.PHONE_HISTORY,
        label_vi="Tỷ lệ hoàn của SĐT",
        value=value,
        contribution=contribution,
    )


def candidate(text, *keys):
    return {"text_vi": text, "signal_keys": list(keys or ["phone_return_rate"])}


def test_history_counts_require_facts_on_the_cited_signal():
    record = candidate("SĐT này đã hoàn 2 trên 4 đơn trước đây.")
    assert not check_reasons([record], [signal()]).reasons
    result = check_reasons(
        [record], [signal()], facts={"phone_return_rate": {"returned_orders": 2, "past_orders": 4}}
    )
    assert result.reasons == [Reason.model_validate(record)]
    assert not check_reasons(
        [record], [signal()], facts={"unrelated": {"returned_orders": 2, "past_orders": 4}}
    ).reasons


@pytest.mark.parametrize("text", ["Tỷ lệ hoàn trước đây là 50%.", "Tỷ lệ hoàn trước đây là 0,5."])
def test_percentage_and_decimal_rate_formats_are_equivalent(text):
    assert check_reasons([candidate(text)], [signal()]).reasons


@pytest.mark.parametrize("formatted", ["1.500.000đ", "1,500,000 VND", "1 500 000 đồng"])
def test_amount_grouping_formats_are_equivalent(formatted):
    record = candidate(f"Giá trị đơn hàng là {formatted}.", "order_value_vnd")
    assert check_reasons([record], [signal("order_value_vnd", 1500000)]).reasons


def test_time_formats_are_equivalent():
    record = candidate("Đơn được đặt lúc 21h30.", "placed_hour")
    assert check_reasons(
        [record], [signal("placed_hour", 21)], facts={"placed_hour": {"placed_time": "21:30"}}
    ).reasons
    wrong = candidate("Đơn được đặt lúc 21h45.", "placed_hour")
    assert not check_reasons(
        [wrong], [signal("placed_hour", 21)], facts={"placed_hour": {"placed_time": "21:30"}}
    ).reasons


@pytest.mark.parametrize(
    "text",
    [
        "SĐT có rủi ro cao.",
        "SĐT co rui ro cao.",
        "SĐT có 41 điểm.",
        "Risk score is high.",
        "Probability is 50%.",
        "Nên gọi xác nhận.",
        "Can yeu cau coc.",
        "Hold the order for review.",
        "Ship now.",
        "Send a confirmation link.",
        "Đơn thuộc mức rất cao.",
    ],
)
def test_score_tier_probability_and_action_language_is_rejected(text):
    assert not check_reasons([candidate(text)], [signal()]).reasons


def test_shape_unknown_keys_negative_signals_and_duplicates_are_dropped():
    records = [
        candidate("  "),
        candidate("x" * 201),
        {"text_vi": "Địa chỉ thiếu số nhà.", "signal_keys": []},
        candidate("Địa chỉ thiếu số nhà.", "unknown"),
        candidate("Tỷ lệ hoàn trước đây là 50%."),
        candidate("SĐT có tỷ lệ hoàn là 50%."),
        candidate("Khách có hỏi kỹ.", "conversation_asked_details"),
    ]
    result = check_reasons(records, [signal(), signal("conversation_asked_details", True, -0.01)])
    assert len(result.reasons) == 1
    assert result.dropped == {"shape": 3, "unknown_signal": 2, "duplicate_signals": 1}
    assert all(
        note in {"shape", "unknown_signal", "duplicate_signals"} for note in result.rejection_notes
    )


def test_false_boolean_cannot_support_its_affirmative_label():
    record = candidate("Địa chỉ thiếu số nhà.", "address_missing_house_number")
    result = check_reasons([record], [signal("address_missing_house_number", False)])
    assert not result.reasons
    assert result.dropped == {"contradicted_signal": 1}


@pytest.mark.parametrize(
    "text",
    [
        "Địa chỉ thiếu số nhà.",
        "Địa chỉ thiếu phường/xã.",
        "Địa chỉ mơ hồ.",
        "Khách chốt đơn vội.",
        "Tên trong hội thoại khác tên người đặt.",
        "Đơn hàng chưa có tiền trả trước.",
    ],
)
def test_known_boolean_claim_requires_its_own_signal_citation(text):
    assert not check_reasons([candidate(text)], [signal()]).reasons


def test_known_claim_cannot_use_an_uncited_existing_signal():
    signals = [signal(), signal("address_missing_house_number", True)]
    assert not check_reasons([candidate("Địa chỉ thiếu số nhà.")], signals).reasons


def test_keeps_at_most_three_in_contribution_order():
    signals = [signal(f"metric_{i}", i, i / 10) for i in range(1, 5)]
    records = [candidate(f"Giá trị ghi nhận là {i}.", f"metric_{i}") for i in range(1, 5)]
    result = check_reasons(records, signals)
    assert [reason.signal_keys for reason in result.reasons] == [
        ["metric_4"],
        ["metric_3"],
        ["metric_2"],
    ]
    assert result.dropped == {"count": 1}


@pytest.mark.parametrize("tier", [RiskTier.HIGH, RiskTier.VERY_HIGH])
def test_high_tiers_drop_location_only_explanations(tier):
    record = candidate("Khu vực giao hàng có tỷ lệ hoàn 50%.", "province_return_rate")
    location = signal("province_return_rate", 0.5, group=SignalGroup.CONTEXT)
    assert not check_reasons([record], [location], tier=tier).reasons
    assert check_reasons([record], [location], tier=RiskTier.MEDIUM).reasons


def test_high_tier_retains_non_location_reason_when_top_three_are_locations():
    signals = [signal(key, 0.5, 0.3) for key in ["province", "region", "delivery_area"]]
    signals.append(signal("address_missing_house_number", True, 0.01))
    records = [
        candidate("Tỷ lệ hoàn tại khu vực là 50%.", key)
        for key in ["province", "region", "delivery_area"]
    ]
    records.append(candidate("Địa chỉ thiếu số nhà.", "address_missing_house_number"))
    result = check_reasons(records, signals, tier=RiskTier.HIGH)
    assert len(result.reasons) == 3
    assert any(reason.signal_keys == ["address_missing_house_number"] for reason in result.reasons)


def test_non_location_context_is_not_classified_by_group():
    record = candidate("Danh mục sản phẩm ghi nhận là áo.", "product_category")
    assert check_reasons(
        [record], [signal("product_category", "áo", group=SignalGroup.CONTEXT)], tier=RiskTier.HIGH
    ).reasons


def test_rejection_notes_never_contain_candidate_text():
    result = check_reasons([candidate("Nên gọi người mua Mẫu Bí Mật.", "unknown")], [signal()])
    assert "Mẫu Bí Mật" not in repr(result.rejection_notes)


@pytest.mark.parametrize("text", ["SĐT này đã hoàn99 đơn.", "SĐT84000000001 có đơn trước đây."])
def test_embedded_numeric_claims_are_not_skipped(text):
    result = check_reasons([candidate(text)], [signal()])
    assert not result.reasons
    assert result.dropped == {"unsupported_number": 1}


def test_repeated_whitespace_cannot_hide_decision_language():
    result = check_reasons([candidate("SĐT có rủi   ro cao.")], [signal()])
    assert not result.reasons
    assert result.dropped == {"decision_language": 1}
