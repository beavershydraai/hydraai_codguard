import type { OrderSummary } from '@/api/gen'

import { DECISION_ACTION_LABELS, ORDER_STATUS_LABELS, RISK_TIER_LABELS, SALES_CHANNEL_LABELS } from './labels'

const HEADER = [
  'Order ID',
  'Channel',
  'Buyer',
  'Phone',
  'COD (VND)',
  'Risk tier',
  'Score',
  'Action',
  'Status',
  'Placed at',
]

function cell(value: string | number | null | undefined): string {
  const text = value == null ? '' : String(value)
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

/** CSV of the given orders, with a BOM so Excel reads non-ASCII text (such as Vietnamese names) as UTF-8. */
export function ordersToCsv(orders: OrderSummary[]): string {
  const rows = orders.map((o) => [
    o.external_id ?? o.id,
    SALES_CHANNEL_LABELS[o.channel],
    o.buyer_name,
    o.buyer_phone,
    o.cod_amount_vnd,
    o.tier ? RISK_TIER_LABELS[o.tier] : '',
    o.risk_score,
    o.current_action ? DECISION_ACTION_LABELS[o.current_action] : '',
    ORDER_STATUS_LABELS[o.status],
    o.placed_at,
  ])
  return '﻿' + [HEADER, ...rows].map((r) => r.map(cell).join(',')).join('\r\n') + '\r\n'
}
