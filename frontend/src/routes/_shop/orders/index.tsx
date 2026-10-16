import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { PlusIcon, TruckIcon, UploadIcon } from 'lucide-react'
import { useState } from 'react'

import { importDeliveryOutcomes, importOrders, type OrderStatus, type RiskTier } from '@/api/gen'
import { listOrdersInfiniteOptions } from '@/api/gen/@tanstack/react-query.gen'
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
  q?: string
  sort?: OrderSort
}

/** Keeps only known values; accepts a single value or a list. */
function pick<T extends string>(value: unknown, allowed: readonly T[]): T[] | undefined {
  const list = (Array.isArray(value) ? value : [value]).filter((v): v is T => allowed.includes(v as T))
  return list.length ? list : undefined
}

const TIERS = Object.keys(RISK_TIER_LABELS) as RiskTier[]
const STATUSES = Object.keys(ORDER_STATUS_LABELS) as OrderStatus[]
const BRANCHES = Object.keys(BRANCH_LABELS)
const SORTS: OrderSort[] = ['-placed_at', 'placed_at', '-updated_at', '-risk_score', '-cod_amount_vnd']
const PAGE_SIZE = 100
const REFRESH_MS = 10_000

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

// The server filters, searches, sorts and pages (E7.2): 100 orders at a time, "Load more" for the
// next 100. Filters, search and sort live in the URL.
export const Route = createFileRoute('/_shop/orders/')({
  staticData: { crumb: 'Orders' },
  validateSearch: (search: Record<string, unknown>): OrdersSearch => ({
    tier: pick(search.tier, TIERS),
    status: pick(search.status, STATUSES),
    branch: pick(search.branch, BRANCHES),
    q: typeof search.q === 'string' && search.q.trim() ? search.q.trim() : undefined,
    sort: pick(search.sort, SORTS)?.[0],
  }),
  component: OrdersPage,
})

function OrdersPage() {
  const search = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })
  const sort = search.sort ?? '-placed_at'
  const query = {
    sort,
    limit: PAGE_SIZE,
    status: search.status,
    tier: search.tier,
    branch: search.branch,
    q: search.q,
  }
  const { data, error, isPending, refetch, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useInfiniteQuery({
      ...listOrdersInfiniteOptions({ query }),
      initialPageParam: { query: {} },
      getNextPageParam: (last) => last.next_cursor ?? undefined,
      // New orders (intake, the simulator) show up on their own: the first page is fetched again
      // every 10 s in the background while the tab is visible. The rows on screen stay until the
      // new ones arrive, so nothing flickers. Paused once "Load more" has loaded further pages.
      refetchInterval: (q) => ((q.state.data?.pages.length ?? 0) > 1 ? false : REFRESH_MS),
    })
  const orders = data?.pages.flatMap((page) => page.items) ?? []
  const queryClient = useQueryClient()
  const [panel, setPanel] = useState<'create' | 'import' | 'delivery' | null>(null)
  const close = (open: boolean) => !open && setPanel(null)

  const filters: OrderFilters = {
    tiers: search.tier ?? [],
    statuses: search.status ?? [],
    branches: search.branch ?? [],
  }
  const setSearch = (next: OrdersSearch) =>
    navigate({ search: (current) => ({ ...current, ...next }), replace: true })
  const setFilters = ({ tiers, statuses, branches }: OrderFilters) =>
    setSearch({
      tier: tiers.length ? tiers : undefined,
      status: statuses.length ? statuses : undefined,
      branch: branches.length ? branches : undefined,
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
        orders={orders}
        total={Math.max(data?.pages[0]?.total ?? 0, orders.length)}
        isLoading={isPending}
        filters={filters}
        onFiltersChange={setFilters}
        search={search.q ?? ''}
        onSearchChange={(q) => setSearch({ q: q || undefined })}
        sort={sort}
        onSortChange={(next) => setSearch({ sort: next === '-placed_at' ? undefined : next })}
        hasMore={hasNextPage}
        isLoadingMore={isFetchingNextPage}
        onLoadMore={() => void fetchNextPage()}
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
