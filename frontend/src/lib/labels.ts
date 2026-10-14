import type { DecisionAction, OrderStatus, RiskTier, SalesChannel } from '@/api/gen'

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

const vnd = new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' })
const dateTime = new Intl.DateTimeFormat('vi-VN', {
  dateStyle: 'short',
  timeStyle: 'short',
  timeZone: 'Asia/Ho_Chi_Minh',
})

export const formatVnd = (amount: number) => vnd.format(amount)
export const formatDateTime = (iso: string) => dateTime.format(new Date(iso))
