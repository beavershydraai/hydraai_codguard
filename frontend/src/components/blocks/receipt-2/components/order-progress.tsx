import type { OrderStatus } from '@/api/gen'
import { type ProgressStage, ProgressSteps } from '@/components/progress-steps'

// Where the order is in its life: received, checked with the buyer when needed, cleared, shipped,
// delivered. The steps follow the status.

const WAITING_TITLE: Partial<Record<OrderStatus, string>> = {
  awaiting_confirmation: 'Awaiting confirmation',
  awaiting_deposit: 'Awaiting deposit',
  pending_review: 'In review',
}

function stagesFor(status: OrderStatus): ProgressStage[] {
  const at = (index: number, title?: string): ProgressStage[] =>
    ['Received', 'Checked', 'Cleared to ship', 'Shipped', 'Delivered'].map((name, i) => ({
      title: i === index && title ? title : name,
      state: i < index ? 'done' : i === index ? 'current' : 'todo',
    }))
  switch (status) {
    case 'new':
      return at(1, 'Scoring')
    case 'awaiting_confirmation':
    case 'awaiting_deposit':
    case 'pending_review':
      return at(1, WAITING_TITLE[status]).map((s) => (s.state === 'current' ? { ...s, state: 'waiting' } : s))
    case 'cleared_to_ship':
      return at(3)
    case 'shipped':
      return at(4, 'In delivery').map((s) => (s.state === 'current' ? { ...s, state: 'waiting' } : s))
    case 'delivered':
      return at(5)
    case 'delivery_failed':
      return at(4).map((s, i) => (i === 4 ? { title: 'Delivery failed', state: 'failed' } : s))
    case 'cancelled':
      return [
        { title: 'Received', state: 'done' },
        { title: 'Cancelled', state: 'failed' },
      ]
  }
}

export function OrderProgress({ status }: { status: OrderStatus }) {
  return <ProgressSteps stages={stagesFor(status)} label="Order progress" />
}
