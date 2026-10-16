import { Link, useNavigate } from '@tanstack/react-router'
import { type Row } from '@tanstack/react-table'
import { CopyIcon, EyeIcon, GiftIcon, MoreHorizontalIcon } from 'lucide-react'
import { memo } from 'react'
import { toast } from 'sonner'

import type { OrderSummary } from '@/api/gen'
import { type DataGridFeatures } from '@/components/reui/data-grid/data-grid'
import { TierBadge } from '@/components/tier-badge'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useCopyToClipboard } from '@/hooks/use-copy-to-clipboard'
import { formatMoney, SALES_CHANNEL_LABELS } from '@/lib/labels'

type OrderRow = Row<DataGridFeatures, OrderSummary>

export const OrderCell = memo(function OrderCell({ row }: { row: OrderRow }) {
  const o = row.original
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <Link
        to="/orders/$orderId"
        params={{ orderId: o.id }}
        className="line-clamp-1 font-medium text-foreground hover:text-primary hover:underline"
      >
        {o.external_id ?? o.id}
      </Link>
      <span className="line-clamp-1 text-xs text-muted-foreground">{SALES_CHANNEL_LABELS[o.channel]}</span>
    </div>
  )
})

export const BuyerCell = memo(function BuyerCell({ row }: { row: OrderRow }) {
  const o = row.original
  return (
    <div className="flex items-center gap-2">
      <Avatar className="size-8 shrink-0">
        <AvatarFallback>
          {o.buyer_name
            .split(' ')
            .slice(-2)
            .map((n) => n[0])
            .join('')}
        </AvatarFallback>
      </Avatar>
      <div className="min-w-0">
        <div className="flex items-center gap-1">
          <span className="line-clamp-1 font-medium text-foreground">{o.buyer_name}</span>
          {o.is_gift && (
            <Tooltip>
              <TooltipTrigger
                render={
                  <span className="inline-flex shrink-0 text-muted-foreground" aria-label="Gift order" />
                }
              >
                <GiftIcon className="size-3.5" aria-hidden="true" />
              </TooltipTrigger>
              <TooltipContent side="top">Gift order: verify with the buyer only</TooltipContent>
            </Tooltip>
          )}
        </div>
        <div className="line-clamp-1 text-xs text-muted-foreground tabular-nums">{o.buyer_phone}</div>
      </div>
    </div>
  )
})

export const AmountCell = memo(function AmountCell({ row }: { row: OrderRow }) {
  const o = row.original
  const prepaid = o.total_vnd - o.cod_amount_vnd
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="font-medium text-foreground tabular-nums">
        {formatMoney(o.cod_amount_vnd, o.currency)}
      </span>
      {prepaid > 0 && (
        <span className="text-xs text-muted-foreground tabular-nums">
          Prepaid {formatMoney(prepaid, o.currency)}
        </span>
      )}
    </div>
  )
})

export const RiskCell = memo(function RiskCell({ row }: { row: OrderRow }) {
  const o = row.original
  if (!o.tier) return <span className="text-muted-foreground">Not scored</span>
  return (
    <div className="flex items-center gap-1.5">
      <TierBadge tier={o.tier} />
      {o.risk_score != null && (
        <span className="text-xs text-muted-foreground tabular-nums">{o.risk_score}</span>
      )}
    </div>
  )
})

export function ActionsCell({ row }: { row: OrderRow }) {
  const { copyToClipboard } = useCopyToClipboard()
  const navigate = useNavigate()
  const code = row.original.external_id ?? row.original.id

  const handleCopy = () => {
    copyToClipboard(code)
    toast.success('Order ID copied', { description: code })
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button size="icon" variant="ghost" className="size-7" aria-label={`Actions for order ${code}`} />
        }
      >
        <MoreHorizontalIcon aria-hidden="true" />
      </DropdownMenuTrigger>
      <DropdownMenuContent side="bottom" align="end" className="w-44">
        <DropdownMenuGroup>
          <DropdownMenuItem
            onClick={() => navigate({ to: '/orders/$orderId', params: { orderId: row.original.id } })}
          >
            <EyeIcon className="size-4" aria-hidden="true" />
            View details
          </DropdownMenuItem>
          <DropdownMenuItem onClick={handleCopy}>
            <CopyIcon className="size-4" aria-hidden="true" />
            Copy order ID
          </DropdownMenuItem>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
