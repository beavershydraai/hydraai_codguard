import { useNavigate } from '@tanstack/react-router'
import {
  type ExpandedState,
  type PaginationState,
  type RowSelectionState,
  type SortingState,
  useTable,
} from '@tanstack/react-table'
import {
  CheckCheckIcon,
  ClockAlertIcon,
  InboxIcon,
  ListChecksIcon,
  PartyPopperIcon,
  RefreshCwIcon,
  SearchIcon,
  WalletIcon,
  XIcon,
} from 'lucide-react'
import { useMemo, useState } from 'react'

import type { OrderSummary } from '@/api/gen'
import { EmptyState } from '@/components/empty-state'
import { Badge } from '@/components/reui/badge'
import { DataGrid, dataGridFeatures } from '@/components/reui/data-grid/data-grid'
import { DataGridPagination } from '@/components/reui/data-grid/data-grid-pagination'
import { DataGridScrollArea } from '@/components/reui/data-grid/data-grid-scroll-area'
import { DataGridTable } from '@/components/reui/data-grid/data-grid-table'
import {
  Frame,
  FrameDescription,
  FrameFooter,
  FrameHeader,
  FramePanel,
  FrameTitle,
} from '@/components/ui/frame'
import {
  Timeline,
  TimelineContent,
  TimelineIndicator,
  TimelineItem,
  TimelineSeparator,
} from '@/components/reui/timeline'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field'
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from '@/components/ui/input-group'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useNow } from '@/hooks/use-now'
import { formatDateTime, formatVnd } from '@/lib/labels'
import { cn } from '@/lib/utils'

import {
  createReviewColumns,
  groupByReason,
  REVIEW_DECISIONS,
  type ReviewDecision,
  type ReviewRow,
  WAIT_WARNING_MS,
} from './review-columns'
import { SummaryTiles } from './summary-tiles'

// Manual review queue (E7.4), adapted from ReUI solution-agents-5 (approval inbox): a header with
// live counts, summary tiles, the queue grid with bulk selection and a decision bar, a reason
// dialog (every override needs a reason, E4.5) and the decisions made in this session.

export type SessionDecision = {
  at: string
  orderLabel: string
  action: ReviewDecision
  reason: string
  ok: boolean
}

type PendingDecision = { orders: OrderSummary[]; action: ReviewDecision }

export function ReviewInbox({
  orders,
  isLoading,
  decisions,
  onRefresh,
  onDecide,
  onAccept,
}: {
  orders: OrderSummary[]
  isLoading: boolean
  decisions: SessionDecision[]
  onRefresh: () => void
  /** Accepts the contact the engine suggested for one order. */
  onAccept: (order: OrderSummary) => void
  /** Applies one decision with its reason to the given orders. */
  onDecide: (orders: OrderSummary[], action: ReviewDecision, reason: string) => Promise<void>
}) {
  const navigate = useNavigate()
  const [pending, setPending] = useState<PendingDecision | null>(null)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  const now = useNow()
  const late = orders.filter((o) => now - Date.parse(o.updated_at) > WAIT_WARNING_MS)
  const highRisk = orders.filter((o) => o.tier === 'high' || o.tier === 'very_high')
  const held = orders.reduce((sum, o) => sum + o.cod_amount_vnd, 0)
  const oldest = [...orders].sort((a, b) => a.updated_at.localeCompare(b.updated_at))[0]

  const ask = (targets: OrderSummary[], action: ReviewDecision) => {
    setPending({ orders: targets, action })
    setReason('')
  }

  return (
    <TooltipProvider delay={200}>
      <div className="@container w-full">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 flex-col gap-0.5">
            <div className="flex items-center gap-2.5">
              <h1 className="text-lg leading-tight font-semibold tracking-tight">Review queue</h1>
              <span className="flex items-center gap-1.5">
                <span className="relative flex size-2 shrink-0" aria-hidden="true">
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-500/60" />
                  <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
                </span>
                <span className="hidden text-sm text-muted-foreground sm:block">Live updates</span>
              </span>
            </div>
            <p className="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
              <span className="tabular-nums">{orders.length} pending</span>
              <Dot />
              <span className="tabular-nums">{late.length} waiting over 2 hours</span>
              <Dot />
              <span className="tabular-nums">{highRisk.length} high risk</span>
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button size="icon-sm" variant="ghost" onClick={onRefresh} aria-label="Refresh review queue">
              <RefreshCwIcon aria-hidden="true" />
            </Button>
            <Button
              size="sm"
              disabled={!oldest}
              onClick={() => oldest && navigate({ to: '/orders/$orderId', params: { orderId: oldest.id } })}
            >
              <ListChecksIcon aria-hidden="true" />
              <span className="hidden sm:block">Open oldest order</span>
            </Button>
          </div>
        </div>

        <div className="mt-4 flex flex-col gap-4">
          {/* Summary tiles */}
          <SummaryTiles
            items={[
              {
                title: 'Pending review',
                value: orders.length,
                note: 'Unreachable, unpaid deposit, invalid phone…',
                icon: <InboxIcon aria-hidden="true" />,
              },
              {
                title: 'Waiting over 2 hours',
                value: late.length,
                badge: late.length > 0 ? <Badge variant="destructive-light">Needs action</Badge> : undefined,
                note: 'Since the last update',
                icon: <ClockAlertIcon aria-hidden="true" />,
              },
              {
                title: 'COD on hold',
                value: formatVnd(held),
                note: 'Total COD of the pending orders',
                icon: <WalletIcon aria-hidden="true" />,
              },
              {
                title: 'Handled this session',
                value: decisions.filter((d) => d.ok).length,
                note: 'Each decision records who, when and why',
                icon: <CheckCheckIcon aria-hidden="true" />,
              },
            ]}
          />

          {!isLoading && orders.length === 0 ? (
            <Frame variant="default" spacing="sm" className="w-full">
              <FramePanel>
                <EmptyState
                  icon={PartyPopperIcon}
                  title="No orders need a decision"
                  description="Orders land here when a buyer does not answer, a deposit is not paid, a phone is invalid, or a contact waits for your approval."
                  actions={
                    <Button variant="outline" onClick={() => navigate({ to: '/orders' })}>
                      Go to Orders
                    </Button>
                  }
                />
              </FramePanel>
            </Frame>
          ) : (
            <ReviewQueue orders={orders} isLoading={isLoading} onDecide={ask} onAccept={onAccept} />
          )}

          <RecentDecisions decisions={decisions} />
        </div>
      </div>

      <AlertDialog open={!!pending} onOpenChange={(open) => !open && !busy && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pending &&
                `${REVIEW_DECISIONS.find((d) => d.action === pending.action)!.label}: ${pending.orders.length > 1 ? `${pending.orders.length} orders` : `order ${pending.orders[0]!.external_id ?? pending.orders[0]!.id}`}?`}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pending?.action === 'ship_now' &&
                'The order ships now, with no further contact with the buyer.'}
              {pending?.action === 'require_deposit' &&
                'The buyer gets a deposit request before the shop ships.'}
              {pending?.action === 'cancel' && 'The order is cancelled and not shipped.'} The reason is saved
              to the order's log.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Field>
            <FieldLabel htmlFor="review-reason">Reason</FieldLabel>
            <Textarea
              id="review-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="For example: Called back on Zalo, the buyer confirmed."
              className="min-h-24 resize-none"
            />
            <FieldDescription>Required, at least 3 characters.</FieldDescription>
          </Field>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Back</AlertDialogCancel>
            <AlertDialogAction
              variant={pending?.action === 'cancel' ? 'destructive' : 'default'}
              disabled={reason.trim().length < 3 || busy}
              onClick={async (event) => {
                event.preventDefault()
                if (!pending) return
                setBusy(true)
                await onDecide(pending.orders, pending.action, reason.trim())
                setBusy(false)
                setPending(null)
              }}
            >
              Confirm
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </TooltipProvider>
  )
}

function Dot() {
  return <span className="size-1 shrink-0 rounded-full bg-input" aria-hidden="true" />
}

function ReviewQueue({
  orders,
  isLoading,
  onDecide,
  onAccept,
}: {
  orders: OrderSummary[]
  isLoading: boolean
  onDecide: (orders: OrderSummary[], action: ReviewDecision) => void
  onAccept: (order: OrderSummary) => void
}) {
  const [search, setSearch] = useState('')
  const [lateOnly, setLateOnly] = useState(false)
  const [grouped, setGrouped] = useState(true)
  // Groups start open; orders open one at a time to show their details.
  const [expanded, setExpanded] = useState<ExpandedState>({})
  const isExpanded = (id: string) =>
    expanded === true || (expanded[id] ?? (id.startsWith('group:') ? true : false))
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 10 })
  // Newest first, so an order that just arrived is on the first page.
  const [sorting, setSorting] = useState<SortingState>([{ id: 'updated_at', desc: true }])
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})
  const now = useNow()

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return orders.filter(
      (o) =>
        (!lateOnly || now - Date.parse(o.updated_at) > WAIT_WARNING_MS) &&
        (!needle ||
          [o.external_id, o.id, o.buyer_name, o.buyer_phone].some((v) => v?.toLowerCase().includes(needle))),
    )
  }, [orders, search, lateOnly, now])

  const rows: ReviewRow[] = useMemo(() => (grouped ? groupByReason(filtered) : filtered), [grouped, filtered])
  const columns = useMemo(
    () => createReviewColumns({ onDecide: (order, action) => onDecide([order], action), onAccept }),
    [onDecide, onAccept],
  )
  const expandedMap = Object.fromEntries(
    [...rows.map((r) => r.id), ...filtered.map((o) => o.id)].map((id) => [id, isExpanded(id)]),
  )
  const table = useTable({
    features: dataGridFeatures,
    columns,
    data: rows,
    // Grouped, the whole queue shows at once (at most 200 orders): a page break inside a group
    // would hide part of it.
    manualPagination: grouped,
    state: {
      pagination,
      sorting,
      rowSelection,
      expanded: expandedMap,
    },
    getRowId: (row) => row.id,
    getSubRows: (row) => ('subRows' in row ? row.subRows : undefined),
    getRowCanExpand: () => true,
    pageCount: grouped ? 1 : Math.ceil(filtered.length / pagination.pageSize),
    enableRowSelection: true,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    onExpandedChange: (updater) =>
      setExpanded(typeof updater === 'function' ? updater(expandedMap) : updater),
  })
  const selected = filtered.filter((o) => rowSelection[o.id])

  return (
    <DataGrid
      table={table}
      recordCount={filtered.length}
      isLoading={isLoading}
      emptyMessage="No orders match the filter."
      tableLayout={{ headerSticky: true, dense: true, width: 'auto' }}
      tableClassNames={{
        // A group's own detail row is empty (data-grid-grouping-1); group rows get a muted band.
        body: '[&>tr:has(>td:only-child:empty)]:hidden',
        bodyRow:
          '[&:has([data-review-row=group])>td]:h-11 [&:has([data-review-row=group])>td]:bg-muted/45 [&:has([data-review-row=group])>td]:hover:bg-muted/45',
      }}
    >
      <Frame variant="default" spacing="sm" className="w-full">
        <FrameHeader className="flex-row items-center justify-between gap-3">
          <div className="flex flex-col gap-0.5">
            <FrameTitle className="text-balance">Orders that need a decision</FrameTitle>
            <FrameDescription className="text-xs text-pretty">
              {filtered.length} orders in this list
            </FrameDescription>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
              variant="outline"
              aria-pressed={grouped}
              onClick={() => setGrouped((v) => !v)}
              className={cn(grouped && 'bg-muted')}
            >
              Group by reason
            </Button>
            <Button
              variant="outline"
              aria-pressed={lateOnly}
              onClick={() => setLateOnly((v) => !v)}
              className={cn(lateOnly && 'bg-muted')}
            >
              Waiting over 2 hours
            </Button>
          </div>
        </FrameHeader>
        <FramePanel className="bg-card p-0! shadow-none!">
          <div className="px-4 py-3">
            <InputGroup className="w-full sm:w-64">
              <InputGroupAddon align="inline-start">
                <SearchIcon aria-hidden="true" />
              </InputGroupAddon>
              <InputGroupInput
                placeholder="Search order ID, name, phone…"
                aria-label="Search the review queue"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
              {search && (
                <InputGroupAddon align="inline-end">
                  <InputGroupButton size="icon-xs" aria-label="Clear search" onClick={() => setSearch('')}>
                    <XIcon aria-hidden="true" />
                  </InputGroupButton>
                </InputGroupAddon>
              )}
            </InputGroup>
          </div>
          <Separator />
          {selected.length > 0 && (
            <>
              <div className="flex flex-col gap-3 bg-muted/25 px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex min-w-0 flex-col gap-0.5">
                  <span className="text-sm font-medium">{selected.length} orders selected</span>
                  <span className="text-xs text-muted-foreground">
                    Apply one decision and one reason to the whole group.
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {REVIEW_DECISIONS.map(({ action, label, icon: Icon }) => (
                    <Button
                      key={action}
                      size="sm"
                      variant={action === 'ship_now' ? 'default' : 'outline'}
                      onClick={() => onDecide(selected, action)}
                    >
                      <Icon data-icon="inline-start" aria-hidden="true" />
                      {label}
                    </Button>
                  ))}
                  <Button size="sm" variant="ghost" onClick={() => setRowSelection({})}>
                    Clear selection
                  </Button>
                </div>
              </div>
              <Separator />
            </>
          )}
          <DataGridScrollArea>
            <DataGridTable />
          </DataGridScrollArea>
        </FramePanel>
        {!grouped && (
          <FrameFooter>
            <DataGridPagination
              info="{from}–{to} of {count} orders"
              rowsPerPageLabel="Orders per page"
              previousPageLabel="Previous page"
              nextPageLabel="Next page"
            />
          </FrameFooter>
        )}
      </Frame>
    </DataGrid>
  )
}

function RecentDecisions({ decisions }: { decisions: SessionDecision[] }) {
  return (
    <Frame variant="default" spacing="sm" className="w-full">
      <FrameHeader className="gap-0.5">
        <FrameTitle className="text-balance">Recent decisions</FrameTitle>
        <FrameDescription className="text-xs text-pretty">
          In this session. The full log is on each order.
        </FrameDescription>
      </FrameHeader>
      <FramePanel>
        {decisions.length === 0 ? (
          <p className="text-sm text-muted-foreground">No decisions yet.</p>
        ) : (
          <Timeline defaultValue={decisions.length} className="gap-0">
            {decisions.map((d, index) => (
              <TimelineItem
                key={`${d.at}-${d.orderLabel}`}
                step={index + 1}
                className="group-data-[orientation=vertical]/timeline:ms-5 group-data-[orientation=vertical]/timeline:not-last:pb-4"
              >
                {index < decisions.length - 1 && (
                  <TimelineSeparator className="bg-input group-data-[orientation=vertical]/timeline:-left-3 group-data-[orientation=vertical]/timeline:h-[calc(100%-1.5rem)] group-data-[orientation=vertical]/timeline:-translate-x-1/2 group-data-[orientation=vertical]/timeline:translate-y-5.5" />
                )}
                <TimelineIndicator
                  className={cn(
                    'size-2.5 border-0 group-data-[orientation=vertical]/timeline:top-1.25 group-data-[orientation=vertical]/timeline:-left-3 group-data-[orientation=vertical]/timeline:-translate-x-1/2',
                    d.ok ? (d.action === 'cancel' ? 'bg-destructive' : 'bg-success') : 'bg-warning',
                  )}
                />
                <TimelineContent className="ps-3">
                  <p className="text-sm font-medium">
                    {REVIEW_DECISIONS.find((x) => x.action === d.action)!.label} · {d.orderLabel}
                    {!d.ok && <span className="ms-1.5 text-xs text-destructive">(failed)</span>}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatDateTime(d.at)} · Reason: {d.reason}
                  </p>
                </TimelineContent>
              </TimelineItem>
            ))}
          </Timeline>
        )}
      </FramePanel>
    </Frame>
  )
}
