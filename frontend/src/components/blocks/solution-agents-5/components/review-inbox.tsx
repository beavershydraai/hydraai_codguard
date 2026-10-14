import { useNavigate } from '@tanstack/react-router'
import {
  type PaginationState,
  type RowSelectionState,
  type SortingState,
  useTable,
} from '@tanstack/react-table'
import { ListChecksIcon, RefreshCwIcon, SearchIcon, XIcon } from 'lucide-react'
import { type ReactNode, useMemo, useState } from 'react'

import type { OrderSummary } from '@/api/gen'
import { Badge } from '@/components/reui/badge'
import { DataGrid, dataGridFeatures } from '@/components/reui/data-grid/data-grid'
import { DataGridPagination } from '@/components/reui/data-grid/data-grid-pagination'
import { DataGridScrollArea } from '@/components/reui/data-grid/data-grid-scroll-area'
import { DataGridTable } from '@/components/reui/data-grid/data-grid-table'
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
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field'
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from '@/components/ui/input-group'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useNow } from '@/hooks/use-now'
import { formatDateTime, formatVnd } from '@/lib/labels'
import { cn } from '@/lib/utils'

import { createReviewColumns, REVIEW_DECISIONS, type ReviewDecision, WAIT_WARNING_MS } from './review-columns'

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
}: {
  orders: OrderSummary[]
  isLoading: boolean
  decisions: SessionDecision[]
  onRefresh: () => void
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
    <TooltipProvider delayDuration={200}>
      <div className="@container w-full">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 flex-col gap-0.5">
            <div className="flex items-center gap-2.5">
              <h1 className="text-lg leading-tight font-semibold tracking-tight">Hàng chờ duyệt</h1>
              <span className="flex items-center gap-1.5">
                <span className="relative flex size-2 shrink-0" aria-hidden="true">
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-500/60" />
                  <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
                </span>
                <span className="hidden text-sm text-muted-foreground sm:block">Tự cập nhật</span>
              </span>
            </div>
            <p className="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
              <span className="tabular-nums">{orders.length} đơn chờ</span>
              <Dot />
              <span className="tabular-nums">{late.length} chờ quá 2 giờ</span>
              <Dot />
              <span className="tabular-nums">{highRisk.length} rủi ro cao</span>
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button size="icon-sm" variant="ghost" onClick={onRefresh} aria-label="Làm mới hàng chờ">
              <RefreshCwIcon aria-hidden="true" />
            </Button>
            <Button
              size="sm"
              disabled={!oldest}
              onClick={() => oldest && navigate({ to: '/orders/$orderId', params: { orderId: oldest.id } })}
            >
              <ListChecksIcon aria-hidden="true" />
              <span className="hidden sm:block">Xem đơn chờ lâu nhất</span>
            </Button>
          </div>
        </div>

        <div className="mt-4 flex flex-col gap-4">
          {/* Summary tiles */}
          <div className="grid grid-cols-1 gap-4 @2xl:grid-cols-2 @4xl:grid-cols-4">
            <SummaryTile
              title="Đơn chờ duyệt"
              value={orders.length}
              note="Gọi không được, chưa cọc, SĐT lỗi…"
            />
            <SummaryTile
              title="Chờ quá 2 giờ"
              value={late.length}
              badge={late.length > 0 ? <Badge variant="destructive-light">Cần xử lý</Badge> : undefined}
              note="Tính từ lần cập nhật gần nhất"
            />
            <SummaryTile
              title="Tiền thu hộ đang giữ"
              value={formatVnd(held)}
              note="Tổng COD của các đơn đang chờ"
            />
            <SummaryTile
              title="Đã xử lý trong phiên"
              value={decisions.filter((d) => d.ok).length}
              note="Mỗi quyết định có ghi người, lúc và lý do"
            />
          </div>

          <ReviewQueue orders={orders} isLoading={isLoading} onDecide={ask} />

          <RecentDecisions decisions={decisions} />
        </div>
      </div>

      <AlertDialog open={!!pending} onOpenChange={(open) => !open && !busy && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pending &&
                `${REVIEW_DECISIONS.find((d) => d.action === pending.action)!.label} ${pending.orders.length > 1 ? `${pending.orders.length} đơn` : `đơn ${pending.orders[0]!.external_id ?? pending.orders[0]!.id}`}?`}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pending?.action === 'ship_now' && 'Đơn được gửi đi ngay, không liên hệ người mua thêm.'}
              {pending?.action === 'require_deposit' &&
                'Người mua nhận yêu cầu đặt cọc trước khi shop gửi hàng.'}
              {pending?.action === 'cancel' && 'Đơn bị hủy và không gửi hàng.'} Lý do được ghi vào nhật ký của
              đơn.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Field>
            <FieldLabel htmlFor="review-reason">Lý do</FieldLabel>
            <Textarea
              id="review-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Ví dụ: Đã gọi lại qua Zalo, khách xác nhận."
              className="min-h-24 resize-none"
            />
            <FieldDescription>Bắt buộc, ít nhất 3 ký tự.</FieldDescription>
          </Field>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Hủy bỏ</AlertDialogCancel>
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
              Xác nhận
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

function SummaryTile({
  title,
  value,
  note,
  badge,
}: {
  title: string
  value: ReactNode
  note: string
  badge?: ReactNode
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-5">
        <h3 className="text-sm font-medium text-muted-foreground">{title}</h3>
        <div className="space-y-2.5">
          <div className="flex items-center gap-2.5">
            <span className="text-2xl font-medium tracking-tight tabular-nums">{value}</span>
            {badge}
          </div>
          <Separator />
          <div className="text-xs text-muted-foreground">{note}</div>
        </div>
      </CardContent>
    </Card>
  )
}

function ReviewQueue({
  orders,
  isLoading,
  onDecide,
}: {
  orders: OrderSummary[]
  isLoading: boolean
  onDecide: (orders: OrderSummary[], action: ReviewDecision) => void
}) {
  const [search, setSearch] = useState('')
  const [lateOnly, setLateOnly] = useState(false)
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 10 })
  const [sorting, setSorting] = useState<SortingState>([{ id: 'updated_at', desc: false }])
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

  const columns = useMemo(
    () => createReviewColumns({ onDecide: (order, action) => onDecide([order], action) }),
    [onDecide],
  )
  const table = useTable({
    features: dataGridFeatures,
    columns,
    data: filtered,
    state: { pagination, sorting, rowSelection },
    getRowId: (row) => row.id,
    pageCount: Math.ceil(filtered.length / pagination.pageSize),
    enableRowSelection: true,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
  })
  const selected = filtered.filter((o) => rowSelection[o.id])

  return (
    <DataGrid
      table={table}
      recordCount={filtered.length}
      isLoading={isLoading}
      emptyMessage={orders.length === 0 ? 'Không có đơn nào chờ duyệt. 🎉' : 'Không có đơn khớp bộ lọc.'}
      tableLayout={{ headerSticky: true, dense: true, width: 'auto' }}
    >
      <Card className="w-full gap-0 p-0">
        <CardHeader className="gap-1 border-b px-5 py-4">
          <CardTitle>Đơn cần shop quyết định</CardTitle>
          <CardDescription className="text-xs">{filtered.length} đơn trong danh sách này</CardDescription>
          <CardAction className="self-center">
            <Button
              variant="outline"
              aria-pressed={lateOnly}
              onClick={() => setLateOnly((v) => !v)}
              className={cn(lateOnly && 'bg-muted')}
            >
              Chờ quá 2 giờ
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent className="p-0">
          <div className="px-5 py-3">
            <InputGroup className="w-full sm:w-64">
              <InputGroupAddon align="inline-start">
                <SearchIcon aria-hidden="true" />
              </InputGroupAddon>
              <InputGroupInput
                placeholder="Tìm mã đơn, tên, SĐT…"
                aria-label="Tìm trong hàng chờ"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
              {search && (
                <InputGroupAddon align="inline-end">
                  <InputGroupButton size="icon-xs" aria-label="Xóa tìm kiếm" onClick={() => setSearch('')}>
                    <XIcon aria-hidden="true" />
                  </InputGroupButton>
                </InputGroupAddon>
              )}
            </InputGroup>
          </div>
          <Separator />
          {selected.length > 0 && (
            <>
              <div className="flex flex-col gap-3 bg-muted/25 px-5 py-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex min-w-0 flex-col gap-0.5">
                  <span className="text-sm font-medium">Đã chọn {selected.length} đơn</span>
                  <span className="text-xs text-muted-foreground">
                    Áp dụng một quyết định và một lý do cho cả nhóm.
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
                    Bỏ chọn
                  </Button>
                </div>
              </div>
              <Separator />
            </>
          )}
          <DataGridScrollArea>
            <DataGridTable />
          </DataGridScrollArea>
        </CardContent>
        <CardFooter className="border-t px-5 py-3">
          <DataGridPagination
            info="{from} - {to} trên {count} đơn"
            rowsPerPageLabel="Số đơn mỗi trang"
            previousPageLabel="Trang trước"
            nextPageLabel="Trang sau"
          />
        </CardFooter>
      </Card>
    </DataGrid>
  )
}

function RecentDecisions({ decisions }: { decisions: SessionDecision[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Quyết định gần đây</CardTitle>
        <CardDescription className="text-xs">
          Trong phiên làm việc này. Nhật ký đầy đủ nằm ở từng đơn.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {decisions.length === 0 ? (
          <p className="text-sm text-muted-foreground">Chưa có quyết định nào.</p>
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
                    {!d.ok && <span className="ms-1.5 text-xs text-destructive">(không thành công)</span>}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatDateTime(d.at)} · Lý do: {d.reason}
                  </p>
                </TimelineContent>
              </TimelineItem>
            ))}
          </Timeline>
        )}
      </CardContent>
    </Card>
  )
}
