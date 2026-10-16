"""Enumerations shared by the API contract.

Values are English snake_case. The English UI label of each value is listed in the
enum's docstring, which becomes its description in the OpenAPI document.
"""

from enum import StrEnum


class OrderStatus(StrEnum):
    """Order lifecycle state.

    new: New · cleared_to_ship: Cleared to ship · awaiting_confirmation: Awaiting confirmation ·
    awaiting_deposit: Awaiting deposit · pending_review: Pending review · cancelled: Cancelled ·
    shipped: Shipped · delivered: Delivered · delivery_failed: Delivery failed
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
    """Risk tier. low: Low · medium: Medium · high: High · very_high: Very high"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class DecisionAction(StrEnum):
    """Action chosen by the decision engine or a staff override.

    ship_now: Ship now · send_confirmation_link: Send confirmation link · ai_call: AI call ·
    require_deposit: Require deposit · hold_for_review: Hold for review · cancel: Cancel order
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
    """Signal group. phone_history: Phone history · address_quality: Address quality ·
    order_behavior: Ordering behaviour · conversation: Sales conversation ·
    velocity: Unusual frequency · context: Context · payment: Payment"""

    PHONE_HISTORY = "phone_history"
    ADDRESS_QUALITY = "address_quality"
    ORDER_BEHAVIOR = "order_behavior"
    CONVERSATION = "conversation"
    VELOCITY = "velocity"
    CONTEXT = "context"
    PAYMENT = "payment"


class ContactChannel(StrEnum):
    """How the buyer was contacted. ai_call: AI call · confirmation_link: Confirmation link ·
    deposit_request: Deposit request"""

    AI_CALL = "ai_call"
    CONFIRMATION_LINK = "confirmation_link"
    DEPOSIT_REQUEST = "deposit_request"


class ContactBlockReason(StrEnum):
    """Why the buyer was not contacted.

    expected_loss_below_cost: expected loss below the cost of contact ·
    daily_call_limit: this phone already had an AI call in the last 24 hours ·
    outside_contact_hours: outside contact hours ·
    phone_blocked: phone blocked for 30 days after "I didn't order this" ·
    phone_trusted: phone trusted for 7 days after a confirmation ·
    already_confirmed: order already confirmed ·
    batched: batched into another order's contact within 15 minutes ·
    attempts_exhausted: both call attempts used ·
    manual_approval: the shop approves every AI call (call automation mode "suggest") ·
    below_auto_call_tier: risk tier below the one the shop auto-calls from ·
    cod_out_of_range: amount to collect outside the shop's auto-call range ·
    channel_not_automated: the shop does not auto-call orders from this sales channel ·
    outside_call_window: outside the hours or days the shop allows automatic calls
    """

    EXPECTED_LOSS_BELOW_COST = "expected_loss_below_cost"
    DAILY_CALL_LIMIT = "daily_call_limit"
    OUTSIDE_CONTACT_HOURS = "outside_contact_hours"
    PHONE_BLOCKED = "phone_blocked"
    PHONE_TRUSTED = "phone_trusted"
    ALREADY_CONFIRMED = "already_confirmed"
    BATCHED = "batched"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"
    MANUAL_APPROVAL = "manual_approval"
    BELOW_AUTO_CALL_TIER = "below_auto_call_tier"
    COD_OUT_OF_RANGE = "cod_out_of_range"
    CHANNEL_NOT_AUTOMATED = "channel_not_automated"
    OUTSIDE_CALL_WINDOW = "outside_call_window"


class CallAutomationMode(StrEnum):
    """Who starts a contact (link, AI call, deposit request) the engine chooses.

    suggest: the agent only suggests it; the shop accepts it (default) ·
    auto: automation is on: the agent contacts the buyer by itself, AI calls only inside the
    shop's automation rules
    """

    AUTO = "auto"
    SUGGEST = "suggest"


class Weekday(StrEnum):
    """Day of the week. mon · tue · wed · thu · fri · sat · sun"""

    MON = "mon"
    TUE = "tue"
    WED = "wed"
    THU = "thu"
    FRI = "fri"
    SAT = "sat"
    SUN = "sun"


class CallStatus(StrEnum):
    """Technical state of a call. queued · dialing · in_progress · completed · failed"""

    QUEUED = "queued"
    DIALING = "dialing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class CallOutcome(StrEnum):
    """Exactly one result per completed call (the voice tool's uppercase values map 1:1).

    confirmed: Confirmed · edited: Edited · cancelled: Cancelled · not_ordered: Not ordered ·
    no_answer: No answer · wrong_person: Wrong person · unclear: Unclear
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
    """Action on the buyer confirmation page. confirm: Confirm · edit_address: Change address ·
    cancel: Cancel · not_ordered: I didn't order this"""

    CONFIRM = "confirm"
    EDIT_ADDRESS = "edit_address"
    CANCEL = "cancel"
    NOT_ORDERED = "not_ordered"


class DeliveryResult(StrEnum):
    """Delivery result from the carrier. Only refused and unreachable count as a failed
    delivery for training; carrier_issue and shop_issue do not.

    delivered: Delivered · refused: Buyer refused · unreachable: Buyer unreachable ·
    carrier_issue: Carrier issue · shop_issue: Shop issue
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
    """Shop role. owner: Shop owner (can change the policy and costs) · staff: Staff"""

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
