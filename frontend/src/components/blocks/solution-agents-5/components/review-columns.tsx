import { Link } from '@tanstack/react-router'
import { type ColumnDef } from '@tanstack/react-table'
import { BanIcon, CheckIcon, PhoneCallIcon, WalletIcon } from 'lucide-react'

import type { DecisionAction, OrderSummary, ReviewReason, RiskTier } from '@/api/gen'
import { type DataGridFeatures } from '@/components/reui/data-grid/data-grid'
import { DataGridColumnHeader } from '@/components/reui/data-grid/data-grid-column-header'
import {
  DataGridTableRowSelect,
  DataGridTableRowSelectAll,
} from '@/components/reui/data-grid/data-grid-table'
import { TierBadge } from '@/components/tier-badge'
import { Button } from '@/components/ui/button'
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Badge } from '@/components/reui/badge'
import {
  DECISION_ACTION_LABELS,
  formatMoney,
  formatRelative,
  HARD_RULE_LABELS,
  REVIEW_REASON_LABELS,
  SALES_CHANNEL_LABELS,
} from '@/lib/labels'
import { cn } from '@/lib/utils'

import { ExpandButton } from './review-cells'
import { ReviewDetails } from './review-details'

export type ReviewDecision = Extract<DecisionAction, 'ship_now' | 'require_deposit' | 'cancel'>

export const REVIEW_DECISIONS: { action: ReviewDecision; label: string; icon: typeof CheckIcon }[] = [
  { action: 'ship_now', label: 'Approve to ship', icon: CheckIcon },
  { action: 'require_deposit', label: 'Require deposit', icon: WalletIcon },
  { action: 'cancel', label: 'Cancel order', icon: BanIcon },
]

/** Orders waiting longer than this are flagged, like the block's SLA column. */
export const WAIT_WARNING_MS = 2 * 3_600_000

// Grouping by review reason, adapted from ReUI data-grid-grouping-1: a group is a row whose
// sub-rows are its orders, so it expands, collapses and selects them all at once.

export type ReviewGroup = {
  kind: 'group'
  id: string
  reason: ReviewReason | null
  orders: OrderSummary[]
  subRows: ReviewRow[]
}
export type ReviewRow = OrderSummary | ReviewGroup

export const isGroup = (row: ReviewRow): row is ReviewGroup => 'kind' in row && row.kind === 'group'

/** Short names for group rows; the full sentence shows beside them. */
const GROUP_LABELS: Record<ReviewReason, string> = {
  suggested: 'Suggested contacts',
  invalid_phone: 'Invalid phone',
  no_answer_link: 'No answer to the link',
  no_answer_call: 'No answer to the calls',
  deposit_unpaid: 'Deposit unpaid',
  call_unclear: 'Call ended unclear',
  items_changed: 'Item changes asked',
  wrong_person: 'Wrong person reached',
  attempts_used: 'Call attempts used',
  staff: 'Held by staff',
  other: 'Other',
}

const REASON_ORDER = Object.keys(GROUP_LABELS) as ReviewReason[]
const TIER_RANK: RiskTier[] = ['low', 'medium', 'high', 'very_high']

/** One group per review reason, in the order of `REVIEW_REASON_LABELS`. */
export function groupByReason(orders: OrderSummary[]): ReviewGroup[] {
  const groups = new Map<ReviewReason | null, OrderSummary[]>()
  for (const order of orders) {
    const key = order.review_reason ?? null
    groups.set(key, [...(groups.get(key) ?? []), order])
  }
  return [...groups.entries()]
    .sort(([a], [b]) => (a ? REASON_ORDER.indexOf(a) : 99) - (b ? REASON_ORDER.indexOf(b) : 99))
    .map(([reason, members]) => ({
      kind: 'group',
      id: `group:${reason ?? 'none'}`,
      reason,
      orders: members,
      subRows: members,
    }))
}

const highestTier = (orders: OrderSummary[]) =>
  orders.reduce<RiskTier | null>(
    (top, o) => (o.tier && (!top || TIER_RANK.indexOf(o.tier) > TIER_RANK.indexOf(top)) ? o.tier : top),
    null,
  )

export function createReviewColumns({
  onDecide,
  onAccept,
}: {
  onDecide: (order: OrderSummary, action: ReviewDecision) => void
  /** Accepts the contact the engine suggested (automation off). */
  onAccept: (order: OrderSummary) => void
}): ColumnDef<DataGridFeatures, ReviewRow>[] {
  return [
    {
      id: 'select',
      header: () => <DataGridTableRowSelectAll />,
      cell: ({ row }) => <DataGridTableRowSelect row={row} />,
      enableSorting: false,
      size: 36,
      meta: { headerClassName: 'ps-5!', cellClassName: 'ps-5!' },
    },
    {
      // Expands a group to its orders, or an order to its risk reasons and last call
      // (ReUI c-data-grid-8).
      id: 'expand',
      header: () => <span className="sr-only">Details</span>,
      cell: ({ row }) => {
        const o = row.original
        return (
          <ExpandButton
            expanded={row.getIsExpanded()}
            onToggle={() => row.toggleExpanded()}
            label={isGroup(o) ? 'group' : `order ${o.external_id ?? o.id}`}
          />
        )
      },
      enableSorting: false,
      size: 36,
      meta: {
        expandedContent: (o: ReviewRow) => (isGroup(o) ? null : <ReviewDetails order={o} />),
      },
    },
    {
      id: 'order',
      accessorFn: (o) => (isGroup(o) ? (o.reason ?? '') : (o.external_id ?? o.id)),
      header: ({ column }) => <DataGridColumnHeader column={column} title="Order" />,
      cell: ({ row }) => {
        const o = row.original
        if (isGroup(o)) {
          return (
            <div data-review-row="group" className="flex min-w-0 items-center gap-2">
              <span className="truncate text-sm font-medium">
                {o.reason ? GROUP_LABELS[o.reason] : 'No reason given'}
              </span>
              <Badge variant="outline" className="shrink-0">
                {o.orders.length}
              </Badge>
            </div>
          )
        }
        return (
          <div className="flex min-w-0 flex-col gap-0.5">
            <Link
              to="/orders/$orderId"
              params={{ orderId: o.id }}
              className="font-medium text-foreground hover:text-primary hover:underline"
            >
              {o.external_id ?? o.id}
            </Link>
            <span className="truncate text-xs text-muted-foreground">
              {o.buyer_name} · {SALES_CHANNEL_LABELS[o.channel]}
            </span>
          </div>
        )
      },
      size: 200,
    },
    {
      id: 'risk_score',
      accessorFn: (o) =>
        isGroup(o) ? Math.max(-1, ...o.orders.map((x) => x.risk_score ?? -1)) : (o.risk_score ?? -1),
      header: ({ column }) => <DataGridColumnHeader column={column} title="Risk" />,
      cell: ({ row }) => {
        const o = row.original
        const tier = isGroup(o) ? highestTier(o.orders) : o.tier
        if (!tier) return <span className="text-muted-foreground">—</span>
        return (
          <div className="flex items-center gap-1.5">
            {isGroup(o) && <span className="text-xs text-muted-foreground">Up to</span>}
            <TierBadge tier={tier} />
            {!isGroup(o) && (
              <span className="text-xs text-muted-foreground tabular-nums">{o.risk_score}</span>
            )}
          </div>
        )
      },
      size: 130,
    },
    {
      id: 'cod_amount_vnd',
      accessorFn: (o) =>
        isGroup(o) ? o.orders.reduce((sum, x) => sum + x.cod_amount_vnd, 0) : o.cod_amount_vnd,
      header: ({ column }) => <DataGridColumnHeader column={column} title="COD" />,
      cell: ({ row }) => {
        const o = row.original
        if (isGroup(o)) {
          // One total per currency: the queue mixes the branches' countries.
          const totals = new Map<string, number>()
          for (const x of o.orders)
            totals.set(x.currency ?? 'VND', (totals.get(x.currency ?? 'VND') ?? 0) + x.cod_amount_vnd)
          return (
            <span className="flex flex-col text-sm text-muted-foreground tabular-nums">
              {[...totals].map(([currency, total]) => (
                <span key={currency}>{formatMoney(total, currency)}</span>
              ))}
            </span>
          )
        }
        return <span className="font-medium tabular-nums">{formatMoney(o.cod_amount_vnd, o.currency)}</span>
      },
      size: 130,
    },
    {
      // Why the order is here: what happened (rules), the hard rule that fired, and the AI's
      // summary of the last call. The full reasons are on the order page.
      id: 'review_reason',
      accessorFn: (o) => (isGroup(o) ? (o.reason ?? '') : (o.review_reason ?? '')),
      header: ({ column }) => <DataGridColumnHeader column={column} title="Review reason" />,
      cell: ({ row }) => {
        const o = row.original
        if (isGroup(o)) {
          return (
            <span className="text-xs text-muted-foreground">
              {o.reason ? REVIEW_REASON_LABELS[o.reason] : 'Held for a person to decide'}
            </span>
          )
        }
        return (
          <div className="flex min-w-0 flex-col gap-1 py-0.5">
            {o.suggested_action ? (
              <div className="flex items-center gap-1.5">
                <span className="text-sm font-medium text-primary">
                  Suggested: {DECISION_ACTION_LABELS[o.suggested_action]}
                </span>
                <Button size="xs" variant="outline" onClick={() => onAccept(o)}>
                  Accept
                </Button>
              </div>
            ) : (
              <span className="text-sm">{o.review_reason ? REVIEW_REASON_LABELS[o.review_reason] : '—'}</span>
            )}
            {(o.hard_rules ?? []).map((rule) => (
              <Badge key={rule} variant="destructive-light" size="sm" className="w-fit">
                Hard rule: {HARD_RULE_LABELS[rule]}
              </Badge>
            ))}
            {o.contact_summary && (
              <HoverCard>
                <HoverCardTrigger
                  delay={200}
                  render={
                    <button
                      type="button"
                      className="line-clamp-2 cursor-help text-left text-xs text-muted-foreground"
                    />
                  }
                >
                  AI call: {o.contact_summary}
                </HoverCardTrigger>
                <HoverCardContent side="bottom" align="start" className="w-80">
                  <p className="mb-1 flex items-center gap-1.5 font-medium">
                    <PhoneCallIcon className="size-3.5" aria-hidden="true" />
                    Summary of the last AI call
                  </p>
                  <p className="text-muted-foreground">{o.contact_summary}</p>
                </HoverCardContent>
              </HoverCard>
            )}
          </div>
        )
      },
      enableSorting: false,
      size: 380,
    },
    {
      id: 'updated_at',
      // A group sorts by its latest order and shows how long its oldest one has waited.
      accessorFn: (o) =>
        isGroup(o)
          ? o.orders
              .map((x) => x.updated_at)
              .sort()
              .at(-1)!
          : o.updated_at,
      header: ({ column }) => <DataGridColumnHeader column={column} title="Waiting since" />,
      cell: ({ row }) => {
        const o = row.original
        const since = isGroup(o) ? o.orders.map((x) => x.updated_at).sort()[0]! : o.updated_at
        const late = Date.now() - Date.parse(since) > WAIT_WARNING_MS
        return (
          <span
            className={cn(
              'text-sm tabular-nums',
              late ? 'font-medium text-destructive' : 'text-muted-foreground',
            )}
          >
            {isGroup(o) && 'Oldest '}
            {formatRelative(since)}
          </span>
        )
      },
      size: 130,
    },
    {
      id: 'actions',
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => {
        const o = row.original
        if (isGroup(o)) return null
        return (
          <div className="flex items-center justify-end gap-1">
            {REVIEW_DECISIONS.map(({ action, label, icon: Icon }) => (
              <Tooltip key={action}>
                <TooltipTrigger
                  render={
                    <Button
                      size="icon-sm"
                      variant={action === 'cancel' ? 'ghost' : 'outline'}
                      aria-label={`${label}: ${o.external_id ?? o.id}`}
                      onClick={() => onDecide(o, action)}
                    />
                  }
                >
                  <Icon aria-hidden="true" />
                </TooltipTrigger>
                <TooltipContent>{label}</TooltipContent>
              </Tooltip>
            ))}
          </div>
        )
      },
      enableSorting: false,
      size: 130,
      meta: { headerClassName: 'pe-5!', cellClassName: 'pe-5!' },
    },
  ]
}
