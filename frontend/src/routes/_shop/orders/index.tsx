import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { type ColumnDef, type PaginationState, type SortingState, useTable } from '@tanstack/react-table'
import { useMemo, useState } from 'react'

import type { ListOrdersData, OrderSummary, RiskTier } from '@/api/gen'
import { listOrdersOptions } from '@/api/gen/@tanstack/react-query.gen'
import { PageHeader } from '@/components/page-header'
import { QueryError } from '@/components/query-error'
import { Badge } from '@/components/reui/badge'
import {
  DataGrid,
  DataGridContainer,
  dataGridFeatures,
  type DataGridFeatures,
} from '@/components/reui/data-grid/data-grid'
import { DataGridColumnHeader } from '@/components/reui/data-grid/data-grid-column-header'
import { DataGridPagination } from '@/components/reui/data-grid/data-grid-pagination'
import { DataGridScrollArea } from '@/components/reui/data-grid/data-grid-scroll-area'
import { DataGridTable } from '@/components/reui/data-grid/data-grid-table'
import { TierBadge } from '@/components/tier-badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  DECISION_ACTION_LABELS,
  formatDateTime,
  formatVnd,
  ORDER_STATUS_LABELS,
  RISK_TIER_LABELS,
} from '@/lib/labels'
import { cn } from '@/lib/utils'

type OrdersSearch = {
  tier?: RiskTier
}

const TIERS = Object.keys(RISK_TIER_LABELS) as RiskTier[]

// One API page, sorted and paged in the browser. Cursor paging for large inboxes comes with E7.2.
const PAGE_LIMIT = 100

const listQuery = ({ tier }: OrdersSearch): ListOrdersData['query'] => ({
  tier: tier ? [tier] : undefined,
  sort: '-placed_at',
  limit: PAGE_LIMIT,
})

export const Route = createFileRoute('/_shop/orders/')({
  staticData: { crumb: 'Đơn hàng' },
  validateSearch: (search: Record<string, unknown>): OrdersSearch => ({
    tier: TIERS.includes(search.tier as RiskTier) ? (search.tier as RiskTier) : undefined,
  }),
  loaderDeps: ({ search }) => search,
  loader: ({ context, deps }) =>
    context.queryClient.prefetchQuery(listOrdersOptions({ query: listQuery(deps) })),
  component: OrdersPage,
})

function OrdersPage() {
  const search = Route.useSearch()
  const navigate = useNavigate()
  const { data, error, isPending } = useQuery(listOrdersOptions({ query: listQuery(search) }))

  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 })
  const [sorting, setSorting] = useState<SortingState>([])
  const items = useMemo(() => data?.items ?? [], [data])

  const table = useTable({
    features: dataGridFeatures,
    columns,
    data: items,
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
  })

  return (
    <>
      <PageHeader title="Đơn hàng" description="Đơn COD đã được chấm điểm rủi ro bom hàng." />

      <div className="mb-4 flex flex-wrap gap-2">
        <FilterLink label="Tất cả" active={!search.tier} search={{}} />
        {TIERS.map((tier) => (
          <FilterLink
            key={tier}
            label={RISK_TIER_LABELS[tier]}
            active={search.tier === tier}
            search={{ tier }}
          />
        ))}
      </div>

      {error ? (
        <QueryError error={error} />
      ) : (
        <DataGrid
          table={table}
          recordCount={items.length}
          isLoading={isPending}
          emptyMessage="Chưa có đơn nào."
          onRowClick={(order) => navigate({ to: '/orders/$orderId', params: { orderId: order.id } })}
          tableLayout={{ headerSticky: true, headerBackground: true }}
        >
          <div className="space-y-3">
            <DataGridContainer>
              <DataGridScrollArea>
                <DataGridTable />
              </DataGridScrollArea>
            </DataGridContainer>
            <DataGridPagination
              info="{from} - {to} trên {count} đơn"
              rowsPerPageLabel="Số đơn mỗi trang"
              previousPageLabel="Trang trước"
              nextPageLabel="Trang sau"
            />
          </div>
        </DataGrid>
      )}
    </>
  )
}

const columns: ColumnDef<DataGridFeatures, OrderSummary>[] = [
  {
    id: 'order',
    accessorFn: (order) => order.external_id ?? order.id,
    header: ({ column }) => <DataGridColumnHeader title="Mã đơn" column={column} />,
    cell: ({ getValue }) => <span className="font-medium">{getValue() as string}</span>,
    meta: { skeleton: <Skeleton className="h-5 w-32" /> },
    size: 180,
  },
  {
    id: 'buyer',
    accessorKey: 'buyer_name',
    header: ({ column }) => <DataGridColumnHeader title="Người mua" column={column} />,
    cell: ({ row }) => (
      <div className="space-y-px">
        <div className="text-foreground">{row.original.buyer_name}</div>
        <div className="text-xs text-muted-foreground">{row.original.buyer_phone}</div>
      </div>
    ),
    meta: { skeleton: <Skeleton className="h-9 w-36" /> },
    size: 200,
  },
  {
    id: 'cod_amount_vnd',
    accessorKey: 'cod_amount_vnd',
    header: ({ column }) => <DataGridColumnHeader title="Thu hộ" column={column} />,
    cell: ({ row }) => <span className="tabular-nums">{formatVnd(row.original.cod_amount_vnd)}</span>,
    meta: { skeleton: <Skeleton className="h-5 w-20" /> },
    size: 130,
  },
  {
    id: 'risk_score',
    accessorKey: 'risk_score',
    header: ({ column }) => <DataGridColumnHeader title="Rủi ro" column={column} />,
    cell: ({ row }) => (row.original.tier ? <TierBadge tier={row.original.tier} /> : '—'),
    meta: { skeleton: <Skeleton className="h-5 w-16" /> },
    size: 110,
  },
  {
    id: 'current_action',
    accessorKey: 'current_action',
    header: ({ column }) => <DataGridColumnHeader title="Hành động" column={column} />,
    cell: ({ row }) =>
      row.original.current_action ? DECISION_ACTION_LABELS[row.original.current_action] : '—',
    meta: { skeleton: <Skeleton className="h-5 w-24" /> },
    size: 150,
  },
  {
    id: 'status',
    accessorKey: 'status',
    header: ({ column }) => <DataGridColumnHeader title="Trạng thái" column={column} />,
    cell: ({ row }) => <Badge variant="outline">{ORDER_STATUS_LABELS[row.original.status]}</Badge>,
    meta: { skeleton: <Skeleton className="h-5 w-24" /> },
    size: 140,
  },
  {
    id: 'placed_at',
    accessorKey: 'placed_at',
    header: ({ column }) => <DataGridColumnHeader title="Đặt lúc" column={column} />,
    cell: ({ row }) => (
      <span className="text-muted-foreground">{formatDateTime(row.original.placed_at)}</span>
    ),
    meta: { skeleton: <Skeleton className="h-5 w-28" /> },
    size: 140,
  },
]

function FilterLink({ label, active, search }: { label: string; active: boolean; search: OrdersSearch }) {
  return (
    <Link
      to="/orders"
      search={search}
      className={cn(
        'rounded-full border px-3 py-1 text-sm',
        active ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted',
      )}
    >
      {label}
    </Link>
  )
}
