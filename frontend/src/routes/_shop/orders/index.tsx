import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { PlusIcon, TruckIcon, UploadIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { importDeliveryOutcomes, importOrders, type OrderStatus, type RiskTier } from '@/api/gen'
import { lastOrdersChangeOptions, listOrdersOptions } from '@/api/gen/@tanstack/react-query.gen'
import {
  type OrderFilters,
  OrdersDataGrid,
  type OrderSort,
} from '@/components/blocks/data-grid-base-1/components/data-grid-view'
import { CreateOrderSheet } from '@/components/orders/create-order-sheet'
import { CsvImportDialog } from '@/components/orders/csv-import-dialog'
import { QueryError } from '@/components/query-error'
import { Button } from '@/components/ui/button'
import { invalidate } from '@/lib/api'
import { BRANCH_LABELS, ORDER_STATUS_LABELS, RISK_TIER_LABELS } from '@/lib/labels'

type OrdersSearch = {
  tier?: RiskTier[]
  status?: OrderStatus[]
  branch?: string[]
  /** Placing-time range, `yyyy-MM-dd`, both ends included. */
  from?: string
  to?: string
  q?: string
  sort?: OrderSort
}

const DAY = /^\d{4}-\d{2}-\d{2}$/
const day = (value: unknown) => (typeof value === 'string' && DAY.test(value) ? value : undefined)

/** Keeps only known values; accepts a single value or a list. */
function pick<T extends string>(value: unknown, allowed: readonly T[]): T[] | undefined {
  const list = (Array.isArray(value) ? value : [value]).filter((v): v is T => allowed.includes(v as T))
  return list.length ? list : undefined
}

const TIERS = Object.keys(RISK_TIER_LABELS) as RiskTier[]
const STATUSES = Object.keys(ORDER_STATUS_LABELS) as OrderStatus[]
const BRANCHES = Object.keys(BRANCH_LABELS)
const SORTS: OrderSort[] = ['-placed_at', 'placed_at', '-updated_at', '-risk_score', '-cod_amount_vnd']
const PAGE_SIZE = 50
const POLL_MS = 5_000

const ORDER_TEMPLATE = [
  [
    'external_id',
    'channel',
    'buyer_name',
    'buyer_phone',
    'address',
    'item_name',
    'quantity',
    'unit_price_vnd',
    'shipping_fee_vnd',
    'prepaid_vnd',
  ],
  [
    'FB-3001',
    'facebook',
    'Nguyễn Văn Mẫu',
    '0000000001',
    'Số 1 ngõ 2, phường Cầu Giấy, Hà Nội',
    'Cotton T-shirt',
    '1',
    '189000',
    '30000',
    '0',
  ],
]
const DELIVERY_TEMPLATE = [
  ['external_id', 'result', 'carrier'],
  ['FB-3001', 'delivered', 'ghn'],
  ['FB-3002', 'refused', 'ghtk'],
]

// The server filters, searches, sorts and pages (E7.2): one page of 50 orders at a time, with
// previous and next. Filters, search and sort live in the URL.
//
// New orders show up on their own: every 5 s, while the tab is visible, the page asks when the
// shop's orders last changed (one document read) and reloads the page it shows only when that
// changed. The rows on screen stay until the new ones arrive, so nothing flickers.
export const Route = createFileRoute('/_shop/orders/')({
  staticData: { crumb: 'Orders' },
  validateSearch: (search: Record<string, unknown>): OrdersSearch => ({
    tier: pick(search.tier, TIERS),
    status: pick(search.status, STATUSES),
    branch: pick(search.branch, BRANCHES),
    from: day(search.from),
    to: day(search.to),
    q: typeof search.q === 'string' && search.q.trim() ? search.q.trim() : undefined,
    sort: pick(search.sort, SORTS)?.[0],
  }),
  component: OrdersPage,
})

function OrdersPage() {
  const search = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })
  const sort = search.sort ?? '-placed_at'
  // Local days, from the start of the first to the end of the last.
  const placedFrom = search.from && search.to ? new Date(`${search.from}T00:00:00`).toISOString() : undefined
  const placedTo = search.from && search.to ? new Date(`${search.to}T23:59:59.999`).toISOString() : undefined
  const query = {
    sort,
    limit: PAGE_SIZE,
    status: search.status,
    tier: search.tier,
    branch: search.branch,
    placed_from: placedFrom,
    placed_to: placedTo,
    q: search.q,
  }
  // The cursor of each page visited so far: back is the previous one, next the page's own.
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined])
  const queryKey = JSON.stringify(query)
  const [lastQueryKey, setLastQueryKey] = useState(queryKey)
  if (queryKey !== lastQueryKey) {
    setLastQueryKey(queryKey)
    setCursors([undefined]) // new filters, search or sort: back to the first page
  }
  const pageIndex = cursors.length - 1
  const { data, error, isPending, isFetching, refetch } = useQuery({
    ...listOrdersOptions({ query: { ...query, cursor: cursors[pageIndex] } }),
    placeholderData: keepPreviousData,
  })
  const orders = data?.items ?? []

  const { data: change } = useQuery({ ...lastOrdersChangeOptions(), refetchInterval: POLL_MS })
  const changedAt = change?.updated_at
  const [seenChange, setSeenChange] = useState(changedAt)
  useEffect(() => {
    if (changedAt === seenChange) return
    setSeenChange(changedAt)
    if (seenChange !== undefined) void refetch()
  }, [changedAt, seenChange, refetch])
  const queryClient = useQueryClient()
  const [panel, setPanel] = useState<'create' | 'import' | 'delivery' | null>(null)
  const close = (open: boolean) => !open && setPanel(null)

  const filters: OrderFilters = {
    tiers: search.tier ?? [],
    statuses: search.status ?? [],
    branches: search.branch ?? [],
    placedFrom: search.from,
    placedTo: search.to,
  }
  const setSearch = (next: OrdersSearch) =>
    navigate({ search: (current) => ({ ...current, ...next }), replace: true })
  const setFilters = ({ tiers, statuses, branches, placedFrom, placedTo }: OrderFilters) =>
    setSearch({
      tier: tiers.length ? tiers : undefined,
      status: statuses.length ? statuses : undefined,
      branch: branches.length ? branches : undefined,
      from: placedFrom,
      to: placedTo,
      // The server filters on a placing-time range only when sorting by placing time.
      ...(placedFrom && !sort.endsWith('placed_at') ? { sort: undefined } : {}),
    })

  if (error) return <QueryError error={error} />

  return (
    <>
      <OrdersDataGrid
        headerActions={
          <>
            <Button variant="outline" size="sm" onClick={() => setPanel('delivery')}>
              <TruckIcon aria-hidden="true" />
              Import delivery results
            </Button>
            <Button variant="outline" size="sm" onClick={() => setPanel('import')}>
              <UploadIcon aria-hidden="true" />
              Import orders
            </Button>
            <Button size="sm" onClick={() => setPanel('create')}>
              <PlusIcon aria-hidden="true" />
              Create order
            </Button>
          </>
        }
        emptyActions={
          <>
            <Button onClick={() => setPanel('import')}>
              <UploadIcon aria-hidden="true" />
              Import orders
            </Button>
            <Button variant="outline" onClick={() => setPanel('create')}>
              <PlusIcon aria-hidden="true" />
              Create order
            </Button>
          </>
        }
        orders={orders}
        total={Math.max(data?.total ?? 0, orders.length)}
        isLoading={isPending}
        filters={filters}
        onFiltersChange={setFilters}
        search={search.q ?? ''}
        onSearchChange={(q) => setSearch({ q: q || undefined })}
        sort={sort}
        onSortChange={(next) => {
          const keepsRange = next.endsWith('placed_at')
          if (search.from && !keepsRange) {
            toast.info('Date filter removed', {
              description: 'A placing-time range works only with sorting by placing time.',
            })
          }
          setSearch({
            sort: next === '-placed_at' ? undefined : next,
            ...(keepsRange ? {} : { from: undefined, to: undefined }),
          })
        }}
        page={pageIndex}
        pageSize={PAGE_SIZE}
        isFetching={isFetching}
        onPrevious={pageIndex > 0 ? () => setCursors((c) => c.slice(0, -1)) : undefined}
        onNext={
          data?.next_cursor ? () => setCursors((c) => [...c, data.next_cursor ?? undefined]) : undefined
        }
        onRefresh={() => void refetch()}
      />
      <CreateOrderSheet open={panel === 'create'} onOpenChange={close} />
      <CsvImportDialog
        open={panel === 'import'}
        onOpenChange={close}
        title="Import orders from a file"
        description="One order per row. Rows whose shop order ID already exists are skipped; new orders are scored right away."
        templateName="order-import-template.csv"
        template={ORDER_TEMPLATE}
        onImport={async (file) => {
          const { data } = await importOrders({ body: { file }, throwOnError: true })
          void invalidate(queryClient, 'listOrders', 'getDashboardSummary')
          return {
            counts: [
              ['Rows', data.received],
              ['Imported', data.imported],
              ['Duplicates', data.duplicates],
              ['Errors', data.rejected?.length ?? 0],
            ],
            rejected: data.rejected ?? [],
          }
        }}
      />
      <CsvImportDialog
        open={panel === 'delivery'}
        onOpenChange={close}
        title="Import delivery results"
        description="Results from GHN, GHTK… update order statuses and phone history. Only refused deliveries and unreachable buyers count as buyer-caused failures."
        templateName="delivery-results-template.csv"
        template={DELIVERY_TEMPLATE}
        onImport={async (file) => {
          const { data } = await importDeliveryOutcomes({ body: { file }, throwOnError: true })
          void invalidate(queryClient, 'listOrders', 'getOrder', 'getDashboardSummary')
          return {
            counts: [
              ['Rows', data.received],
              ['Updated', data.applied],
              ['Unknown orders', data.unknown_orders],
              ['Errors', data.rejected?.length ?? 0],
            ],
            rejected: data.rejected ?? [],
          }
        }}
      />
    </>
  )
}
