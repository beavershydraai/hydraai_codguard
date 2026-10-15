import { Link } from '@tanstack/react-router'
import { type ColumnDef } from '@tanstack/react-table'
import { BanIcon, CheckIcon, WalletIcon } from 'lucide-react'

import type { DecisionAction, OrderSummary } from '@/api/gen'
import { type DataGridFeatures } from '@/components/reui/data-grid/data-grid'
import { DataGridColumnHeader } from '@/components/reui/data-grid/data-grid-column-header'
import {
  DataGridTableRowSelect,
  DataGridTableRowSelectAll,
} from '@/components/reui/data-grid/data-grid-table'
import { TierBadge } from '@/components/tier-badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { DECISION_ACTION_LABELS, formatRelative, formatMoney, SALES_CHANNEL_LABELS } from '@/lib/labels'
import { cn } from '@/lib/utils'

export type ReviewDecision = Extract<DecisionAction, 'ship_now' | 'require_deposit' | 'cancel'>

export const REVIEW_DECISIONS: { action: ReviewDecision; label: string; icon: typeof CheckIcon }[] = [
  { action: 'ship_now', label: 'Approve to ship', icon: CheckIcon },
  { action: 'require_deposit', label: 'Require deposit', icon: WalletIcon },
  { action: 'cancel', label: 'Cancel order', icon: BanIcon },
]

/** Orders waiting longer than this are flagged, like the block's SLA column. */
export const WAIT_WARNING_MS = 2 * 3_600_000

export function createReviewColumns({
  onDecide,
}: {
  onDecide: (order: OrderSummary, action: ReviewDecision) => void
}): ColumnDef<DataGridFeatures, OrderSummary>[] {
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
      id: 'order',
      accessorFn: (o) => o.external_id ?? o.id,
      header: ({ column }) => <DataGridColumnHeader column={column} title="Order" />,
      cell: ({ row }) => (
        <div className="flex min-w-0 flex-col gap-0.5">
          <Link
            to="/orders/$orderId"
            params={{ orderId: row.original.id }}
            className="font-medium text-foreground hover:text-primary hover:underline"
          >
            {row.original.external_id ?? row.original.id}
          </Link>
          <span className="truncate text-xs text-muted-foreground">
            {row.original.buyer_name} · {SALES_CHANNEL_LABELS[row.original.channel]}
          </span>
        </div>
      ),
      size: 200,
    },
    {
      id: 'risk_score',
      accessorFn: (o) => o.risk_score ?? -1,
      header: ({ column }) => <DataGridColumnHeader column={column} title="Risk" />,
      cell: ({ row }) =>
        row.original.tier ? (
          <div className="flex items-center gap-1.5">
            <TierBadge tier={row.original.tier} />
            <span className="text-xs text-muted-foreground tabular-nums">{row.original.risk_score}</span>
          </div>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
      size: 130,
    },
    {
      id: 'cod_amount_vnd',
      accessorKey: 'cod_amount_vnd',
      header: ({ column }) => <DataGridColumnHeader column={column} title="COD" />,
      cell: ({ row }) => (
        <span className="font-medium tabular-nums">
          {formatMoney(row.original.cod_amount_vnd, row.original.currency)}
        </span>
      ),
      size: 130,
    },
    {
      id: 'held_by',
      accessorFn: (o) => o.current_action ?? '',
      header: ({ column }) => <DataGridColumnHeader column={column} title="Current step" />,
      cell: ({ row }) => (
        <span className="text-sm">
          {row.original.current_action ? DECISION_ACTION_LABELS[row.original.current_action] : '—'}
        </span>
      ),
      size: 150,
    },
    {
      id: 'updated_at',
      accessorKey: 'updated_at',
      header: ({ column }) => <DataGridColumnHeader column={column} title="Waiting since" />,
      cell: ({ row }) => {
        const late = Date.now() - Date.parse(row.original.updated_at) > WAIT_WARNING_MS
        return (
          <span
            className={cn(
              'text-sm tabular-nums',
              late ? 'font-medium text-destructive' : 'text-muted-foreground',
            )}
          >
            {formatRelative(row.original.updated_at)}
          </span>
        )
      },
      size: 130,
    },
    {
      id: 'actions',
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => (
        <div className="flex items-center justify-end gap-1">
          {REVIEW_DECISIONS.map(({ action, label, icon: Icon }) => (
            <Tooltip key={action}>
              <TooltipTrigger asChild>
                <Button
                  size="icon-sm"
                  variant={action === 'cancel' ? 'ghost' : 'outline'}
                  aria-label={`${label}: ${row.original.external_id ?? row.original.id}`}
                  onClick={() => onDecide(row.original, action)}
                >
                  <Icon aria-hidden="true" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>{label}</TooltipContent>
            </Tooltip>
          ))}
        </div>
      ),
      enableSorting: false,
      size: 130,
      meta: { headerClassName: 'pe-5!', cellClassName: 'pe-5!' },
    },
  ]
}
