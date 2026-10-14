import type {
  BuyerAction,
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
} from '@/api/gen'

// Vietnamese UI labels, copied from the enum descriptions in api/openapi.yaml.

export const ORDER_STATUS_LABELS: Record<OrderStatus, string> = {
  new: 'Mới',
  cleared_to_ship: 'Được gửi',
  awaiting_confirmation: 'Chờ xác nhận',
  awaiting_deposit: 'Chờ cọc',
  pending_review: 'Chờ duyệt',
  cancelled: 'Đã hủy',
  shipped: 'Đã gửi',
  delivered: 'Giao thành công',
  delivery_failed: 'Giao thất bại',
}

export const RISK_TIER_LABELS: Record<RiskTier, string> = {
  low: 'Thấp',
  medium: 'Trung bình',
  high: 'Cao',
  very_high: 'Rất cao',
}

export const DECISION_ACTION_LABELS: Record<DecisionAction, string> = {
  ship_now: 'Gửi ngay',
  send_confirmation_link: 'Gửi link xác nhận',
  ai_call: 'AI gọi',
  require_deposit: 'Yêu cầu cọc',
  hold_for_review: 'Chờ duyệt',
  cancel: 'Hủy đơn',
}

export const SALES_CHANNEL_LABELS: Record<SalesChannel, string> = {
  facebook: 'Facebook',
  tiktok: 'TikTok',
  zalo: 'Zalo',
  website: 'Website',
  other: 'Khác',
}

export const CALL_OUTCOME_LABELS: Record<CallOutcome, string> = {
  confirmed: 'Xác nhận',
  edited: 'Đã sửa',
  cancelled: 'Hủy',
  not_ordered: 'Không đặt',
  no_answer: 'Không nghe máy',
  wrong_person: 'Nhầm người',
  unclear: 'Không rõ',
}

export const CALL_STATUS_LABELS: Record<CallStatus, string> = {
  queued: 'Đang xếp hàng',
  dialing: 'Đang quay số',
  in_progress: 'Đang gọi',
  completed: 'Đã xong',
  failed: 'Lỗi',
}

export const CONTACT_CHANNEL_LABELS: Record<ContactChannel, string> = {
  ai_call: 'AI gọi',
  confirmation_link: 'Link xác nhận',
  deposit_request: 'Yêu cầu cọc',
}

export const BLOCK_REASON_LABELS: Record<ContactBlockReason, string> = {
  expected_loss_below_cost: 'Rủi ro thấp hơn chi phí liên hệ',
  daily_call_limit: 'Đã gọi SĐT này trong 24 giờ',
  outside_contact_hours: 'Ngoài giờ liên hệ (8h–21h)',
  phone_blocked: 'SĐT đang bị chặn liên hệ',
  phone_trusted: 'SĐT đã xác nhận gần đây (tin tưởng 7 ngày)',
  already_confirmed: 'Đơn đã được xác nhận',
  batched: 'Gộp với đơn khác cùng SĐT trong 15 phút',
  attempts_exhausted: 'Đã gọi đủ 2 lần',
}

export const HARD_RULE_LABELS: Record<HardRule, string> = {
  prepaid_skip: 'Đã trả trước toàn bộ',
  invalid_phone: 'SĐT không hợp lệ',
  high_return_phone: 'SĐT hoàn ≥75% (tối thiểu 3 đơn)',
}

export const SIGNAL_GROUP_LABELS: Record<SignalGroup, string> = {
  phone_history: 'Lịch sử SĐT',
  address_quality: 'Chất lượng địa chỉ',
  order_behavior: 'Hành vi đặt hàng',
  conversation: 'Hội thoại chốt đơn',
  velocity: 'Tần suất bất thường',
  context: 'Ngữ cảnh',
  payment: 'Thanh toán',
}

export const BUYER_ACTION_LABELS: Record<BuyerAction, string> = {
  confirm: 'Xác nhận',
  edit_address: 'Sửa địa chỉ',
  cancel: 'Hủy',
  not_ordered: 'Tôi không đặt',
}

const vnd = new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' })
const dateTime = new Intl.DateTimeFormat('vi-VN', {
  dateStyle: 'short',
  timeStyle: 'short',
  timeZone: 'Asia/Ho_Chi_Minh',
})

export const formatVnd = (amount: number) => vnd.format(amount)
export const formatDateTime = (iso: string) => dateTime.format(new Date(iso))
export const formatPercent = (share: number, digits = 0) =>
  new Intl.NumberFormat('vi-VN', { style: 'percent', maximumFractionDigits: digits }).format(share)

const relative = new Intl.RelativeTimeFormat('vi', { numeric: 'auto' })
/** "5 phút trước", "hôm qua"… */
export function formatRelative(iso: string, now = Date.now()): string {
  const seconds = (Date.parse(iso) - now) / 1000
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ['day', 86_400],
    ['hour', 3_600],
    ['minute', 60],
  ]
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size)
      return relative.format(Math.round(seconds / size), unit).toLocaleLowerCase('vi')
  }
  return 'vừa xong'
}
