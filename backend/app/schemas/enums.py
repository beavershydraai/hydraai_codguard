"""Enumerations shared by the API contract.

Values are English snake_case. The Vietnamese UI label of each value is listed in the
enum's docstring, which becomes its description in the OpenAPI document.
"""

from enum import StrEnum


class OrderStatus(StrEnum):
    """Order lifecycle state.

    new: Mới · cleared_to_ship: Được gửi · awaiting_confirmation: Chờ xác nhận ·
    awaiting_deposit: Chờ cọc · pending_review: Chờ duyệt · cancelled: Đã hủy ·
    shipped: Đã gửi · delivered: Giao thành công · delivery_failed: Giao thất bại
    """

    NEW = "new"
    CLEARED_TO_SHIP = "cleared_to_ship"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    AWAITING_DEPOSIT = "awaiting_deposit"
    PENDING_REVIEW = "pending_review"
    CANCELLED = "cancelled"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    DELIVERY_FAILED = "delivery_failed"


class RiskTier(StrEnum):
    """Risk tier. low: Thấp · medium: Trung bình · high: Cao · very_high: Rất cao"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class DecisionAction(StrEnum):
    """Action chosen by the decision engine or a staff override.

    ship_now: Gửi ngay · send_confirmation_link: Gửi link xác nhận · ai_call: AI gọi ·
    require_deposit: Yêu cầu cọc · hold_for_review: Chờ duyệt · cancel: Hủy đơn
    """

    SHIP_NOW = "ship_now"
    SEND_CONFIRMATION_LINK = "send_confirmation_link"
    AI_CALL = "ai_call"
    REQUIRE_DEPOSIT = "require_deposit"
    HOLD_FOR_REVIEW = "hold_for_review"
    CANCEL = "cancel"


class HardRule(StrEnum):
    """Hard rule that fired before the model.

    prepaid_skip: fully prepaid, not scored · invalid_phone: invalid phone, held for review ·
    high_return_phone: phone with a ≥75% return rate over at least 3 orders, Very High
    """

    PREPAID_SKIP = "prepaid_skip"
    INVALID_PHONE = "invalid_phone"
    HIGH_RETURN_PHONE = "high_return_phone"


class SignalGroup(StrEnum):
    """Signal group. phone_history: Lịch sử SĐT · address_quality: Chất lượng địa chỉ ·
    order_behavior: Hành vi đặt hàng · conversation: Hội thoại · velocity: Tần suất bất thường ·
    context: Ngữ cảnh · payment: Thanh toán"""

    PHONE_HISTORY = "phone_history"
    ADDRESS_QUALITY = "address_quality"
    ORDER_BEHAVIOR = "order_behavior"
    CONVERSATION = "conversation"
    VELOCITY = "velocity"
    CONTEXT = "context"
    PAYMENT = "payment"


class ContactChannel(StrEnum):
    """How the buyer was contacted. ai_call: AI gọi · confirmation_link: Link xác nhận ·
    deposit_request: Yêu cầu cọc"""

    AI_CALL = "ai_call"
    CONFIRMATION_LINK = "confirmation_link"
    DEPOSIT_REQUEST = "deposit_request"


class ContactBlockReason(StrEnum):
    """Why the buyer was not contacted.

    expected_loss_below_cost: lỗ dự kiến thấp hơn chi phí liên hệ ·
    daily_call_limit: đã có 1 cuộc gọi AI tới SĐT này trong 24 giờ ·
    outside_contact_hours: ngoài giờ liên hệ ·
    phone_blocked: SĐT bị chặn 30 ngày sau "Tôi không đặt" ·
    phone_trusted: SĐT đang được tin tưởng 7 ngày sau khi xác nhận ·
    already_confirmed: đơn đã xác nhận · batched: gộp vào lần liên hệ của đơn khác trong 15 phút ·
    attempts_exhausted: đã gọi đủ 2 lần
    """

    EXPECTED_LOSS_BELOW_COST = "expected_loss_below_cost"
    DAILY_CALL_LIMIT = "daily_call_limit"
    OUTSIDE_CONTACT_HOURS = "outside_contact_hours"
    PHONE_BLOCKED = "phone_blocked"
    PHONE_TRUSTED = "phone_trusted"
    ALREADY_CONFIRMED = "already_confirmed"
    BATCHED = "batched"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"


class CallStatus(StrEnum):
    """Technical state of a call. queued · dialing · in_progress · completed · failed"""

    QUEUED = "queued"
    DIALING = "dialing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class CallOutcome(StrEnum):
    """Exactly one result per completed call (the voice tool's uppercase values map 1:1).

    confirmed: Xác nhận · edited: Đã sửa · cancelled: Hủy · not_ordered: Không đặt ·
    no_answer: Không nghe máy · wrong_person: Nhầm người · unclear: Không rõ
    """

    CONFIRMED = "confirmed"
    EDITED = "edited"
    CANCELLED = "cancelled"
    NOT_ORDERED = "not_ordered"
    NO_ANSWER = "no_answer"
    WRONG_PERSON = "wrong_person"
    UNCLEAR = "unclear"


class CallAgent(StrEnum):
    """Who speaks for the shop on a call.

    script: Kịch bản (pre-recorded prompts and TTS; keypad first, speech as fallback) ·
    gemini_live: Gemini Live (free conversation)
    """

    SCRIPT = "script"
    GEMINI_LIVE = "gemini_live"


class CallLanguage(StrEnum):
    """Language of a call. vi: Tiếng Việt · en: Tiếng Anh"""

    VI = "vi"
    EN = "en"


class CallTargetKind(StrEnum):
    """Where the call controller dials.

    sip: a softphone extension on Asterisk · webrtc: a browser tab registered on Asterisk ·
    pstn: a real phone through the SIP trunk (after M4)
    """

    SIP = "sip"
    WEBRTC = "webrtc"
    PSTN = "pstn"


class CallInputMethod(StrEnum):
    """How the buyer gave the answer that decided the outcome.

    dtmf: keypad · voice: speech · none: no answer
    """

    DTMF = "dtmf"
    VOICE = "voice"
    NONE = "none"


class CallFailureReason(StrEnum):
    """Why a call failed technically. A call that rang without an answer is not a failure:
    it completes with outcome no_answer.

    target_unreachable: the softphone or browser is not registered, or the trunk refused ·
    asterisk_unavailable: the controller could not reach Asterisk (ARI) ·
    agent_error: the script or the Gemini Live session failed ·
    controller_error: any other error in the call controller
    """

    TARGET_UNREACHABLE = "target_unreachable"
    ASTERISK_UNAVAILABLE = "asterisk_unavailable"
    AGENT_ERROR = "agent_error"
    CONTROLLER_ERROR = "controller_error"


class CallChangeField(StrEnum):
    """Field the buyer changed during a call."""

    DELIVERY_ADDRESS = "delivery_address"
    RECIPIENT_NAME = "recipient_name"
    ITEM_VARIANT = "item_variant"
    ITEM_QUANTITY = "item_quantity"
    DELIVERY_NOTE = "delivery_note"
    CANCEL_ORDER = "cancel_order"


class BuyerAction(StrEnum):
    """Action on the buyer confirmation page. confirm: Xác nhận · edit_address: Sửa địa chỉ ·
    cancel: Hủy · not_ordered: Tôi không đặt"""

    CONFIRM = "confirm"
    EDIT_ADDRESS = "edit_address"
    CANCEL = "cancel"
    NOT_ORDERED = "not_ordered"


class DeliveryResult(StrEnum):
    """Delivery result from the carrier. Only refused and unreachable count as a failed
    delivery for training; carrier_issue and shop_issue do not.

    delivered: Giao thành công · refused: Người mua từ chối nhận ·
    unreachable: Không liên lạc được · carrier_issue: Lỗi hãng vận chuyển · shop_issue: Lỗi shop
    """

    DELIVERED = "delivered"
    REFUSED = "refused"
    UNREACHABLE = "unreachable"
    CARRIER_ISSUE = "carrier_issue"
    SHOP_ISSUE = "shop_issue"


class SalesChannel(StrEnum):
    """Where the order came from."""

    FACEBOOK = "facebook"
    TIKTOK = "tiktok"
    ZALO = "zalo"
    WEBSITE = "website"
    OTHER = "other"


class Carrier(StrEnum):
    """Delivery carrier."""

    GHN = "ghn"
    GHTK = "ghtk"
    VIETTEL_POST = "viettel_post"
    JT = "jt"
    SPX = "spx"
    OTHER = "other"


class Role(StrEnum):
    """Shop role. owner: Chủ shop (đổi được policy và chi phí) · staff: Nhân viên"""

    OWNER = "owner"
    STAFF = "staff"


class ErrorCode(StrEnum):
    """Machine-readable error code carried in ProblemDetail.code."""

    VALIDATION_ERROR = "validation_error"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    CALL_NOT_ACTIVE = "call_not_active"
    CONTACT_BLOCKED = "contact_blocked"
    ORDER_NOT_EDITABLE = "order_not_editable"
    LINK_EXPIRED = "link_expired"
    LINK_ALREADY_USED = "link_already_used"
    RATE_LIMITED = "rate_limited"
    NOT_IMPLEMENTED = "not_implemented"
