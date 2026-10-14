import { memo } from 'react'

import type { OrderStatus } from '@/api/gen'
import { Badge } from '@/components/reui/badge'
import { ORDER_STATUS_LABELS } from '@/lib/labels'

const statusBadgeVariant: Record<
  OrderStatus,
  'info-outline' | 'success-outline' | 'warning-outline' | 'destructive-outline' | 'success-light' | 'outline'
> = {
  new: 'info-outline',
  cleared_to_ship: 'success-outline',
  awaiting_confirmation: 'warning-outline',
  awaiting_deposit: 'warning-outline',
  pending_review: 'destructive-outline',
  cancelled: 'outline',
  shipped: 'info-outline',
  delivered: 'success-light',
  delivery_failed: 'destructive-outline',
}

export const OrderStatusBadge = memo(function OrderStatusBadge({ status }: { status: OrderStatus }) {
  return <Badge variant={statusBadgeVariant[status]}>{ORDER_STATUS_LABELS[status]}</Badge>
})
