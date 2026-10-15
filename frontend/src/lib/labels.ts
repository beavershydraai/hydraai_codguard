import type {
  BuyerAction,
  CallAutomationMode,
  CallOutcome,
  CallStatus,
  ContactBlockReason,
  ContactChannel,
  DecisionAction,
  HardRule,
  OrderStatus,
  RiskTier,
  SalesChannel,
  SignalGroup,
  Weekday,
} from '@/api/gen'

// English UI labels for the enums in api/openapi.yaml.

export const ORDER_STATUS_LABELS: Record<OrderStatus, string> = {
  new: 'New',
  cleared_to_ship: 'Cleared to ship',
  awaiting_confirmation: 'Awaiting confirmation',
  awaiting_deposit: 'Awaiting deposit',
  pending_review: 'Pending review',
  cancelled: 'Cancelled',
  shipped: 'Shipped',
  delivered: 'Delivered',
  delivery_failed: 'Delivery failed',
}

export const RISK_TIER_LABELS: Record<RiskTier, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  very_high: 'Very high',
}

export const DECISION_ACTION_LABELS: Record<DecisionAction, string> = {
  ship_now: 'Ship now',
  send_confirmation_link: 'Send confirmation link',
  ai_call: 'AI call',
  require_deposit: 'Require deposit',
  hold_for_review: 'Hold for review',
  cancel: 'Cancel order',
}

export const SALES_CHANNEL_LABELS: Record<SalesChannel, string> = {
  facebook: 'Facebook',
  tiktok: 'TikTok',
  zalo: 'Zalo',
  website: 'Website',
  other: 'Other',
}

export const CALL_OUTCOME_LABELS: Record<CallOutcome, string> = {
  confirmed: 'Confirmed',
  edited: 'Edited',
  cancelled: 'Cancelled',
  not_ordered: 'Not ordered',
  no_answer: 'No answer',
  wrong_person: 'Wrong person',
  unclear: 'Unclear',
}

export const CALL_STATUS_LABELS: Record<CallStatus, string> = {
  queued: 'Queued',
  dialing: 'Dialing',
  in_progress: 'In progress',
  completed: 'Completed',
  failed: 'Failed',
}

export const CONTACT_CHANNEL_LABELS: Record<ContactChannel, string> = {
  ai_call: 'AI call',
  confirmation_link: 'Confirmation link',
  deposit_request: 'Deposit request',
}

export const BLOCK_REASON_LABELS: Record<ContactBlockReason, string> = {
  expected_loss_below_cost: 'Risk is below the cost of contact',
  daily_call_limit: 'Phone already called in the last 24 hours',
  outside_contact_hours: 'Outside contact hours (8:00–21:00)',
  phone_blocked: 'Phone is blocked from contact',
  phone_trusted: 'Phone confirmed recently (trusted for 7 days)',
  already_confirmed: 'Order already confirmed',
  batched: 'Batched with another order to the same phone within 15 minutes',
  attempts_exhausted: 'Both call attempts used',
  manual_approval: 'The shop confirms every AI call',
  below_auto_call_tier: 'Risk tier below the one the shop auto-calls from',
  cod_out_of_range: 'Amount outside the auto-call range',
  channel_not_automated: 'No automatic calls for this sales channel',
  outside_call_window: 'Outside the hours set for automatic calls',
}

export const CALL_AUTOMATION_MODE_LABELS: Record<CallAutomationMode, string> = {
  auto: 'Call automatically',
  suggest: 'Suggest, I confirm each call',
}

export const WEEKDAY_LABELS: Record<Weekday, string> = {
  mon: 'Mon',
  tue: 'Tue',
  wed: 'Wed',
  thu: 'Thu',
  fri: 'Fri',
  sat: 'Sat',
  sun: 'Sun',
}

export const COUNTRY_LABELS: Record<string, string> = {
  VN: 'Vietnam',
  SG: 'Singapore',
  PH: 'Philippines',
}

export const HARD_RULE_LABELS: Record<HardRule, string> = {
  prepaid_skip: 'Fully prepaid',
  invalid_phone: 'Invalid phone number',
  high_return_phone: 'Phone with ≥75% returns (at least 3 orders)',
}

export const SIGNAL_GROUP_LABELS: Record<SignalGroup, string> = {
  phone_history: 'Phone history',
  address_quality: 'Address quality',
  order_behavior: 'Ordering behaviour',
  conversation: 'Sales conversation',
  velocity: 'Unusual frequency',
  context: 'Context',
  payment: 'Payment',
}

export const BUYER_ACTION_LABELS: Record<BuyerAction, string> = {
  confirm: 'Confirm',
  edit_address: 'Change address',
  cancel: 'Cancel',
  not_ordered: "I didn't order this",
}

const vnd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'VND' })
const dateTime = new Intl.DateTimeFormat('en-GB', {
  dateStyle: 'short',
  timeStyle: 'short',
  timeZone: 'Asia/Ho_Chi_Minh',
})

export const formatVnd = (amount: number) => vnd.format(amount)

// Amounts are integers in the currency's minor unit: VND has none, SGD and PHP are in cents.
const MINOR_UNIT: Record<string, number> = { VND: 1, SGD: 100, PHP: 100 }
/** A typed amount ("12.50") in the currency's minor unit (1250 cents); 0 when not a number. */
export const toMinor = (value: string, currency = 'VND') =>
  Math.max(0, Math.round((Number(value.replace(/[^\d.]/g, '')) || 0) * (MINOR_UNIT[currency] ?? 1)))
/** A stored amount as the owner types it: 1250 cents → "12.5". */
export const fromMinor = (amount: number, currency = 'VND') => String(amount / (MINOR_UNIT[currency] ?? 1))
export const CURRENCY_SYMBOLS: Record<string, string> = { VND: '₫', SGD: 'S$', PHP: '₱' }
const money = new Map<string, Intl.NumberFormat>()
/** An order amount in its own currency (VN, SG and PH branches). */
export function formatMoney(amount: number, currency = 'VND'): string {
  let format = money.get(currency)
  if (!format) {
    format = new Intl.NumberFormat('en-US', { style: 'currency', currency })
    money.set(currency, format)
  }
  return format.format(amount / (MINOR_UNIT[currency] ?? 1))
}
export const formatDateTime = (iso: string) => dateTime.format(new Date(iso))
export const formatPercent = (share: number, digits = 0) =>
  new Intl.NumberFormat('en-US', { style: 'percent', maximumFractionDigits: digits }).format(share)

const relative = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
/** "5 minutes ago", "yesterday"… */
export function formatRelative(iso: string, now = Date.now()): string {
  const seconds = (Date.parse(iso) - now) / 1000
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ['day', 86_400],
    ['hour', 3_600],
    ['minute', 60],
  ]
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit)
  }
  return 'just now'
}
