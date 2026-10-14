import { useQuery } from '@tanstack/react-query'
import { createFileRoute, useNavigate } from '@tanstack/react-router'

import type { OrderStatus, RiskTier } from '@/api/gen'
import { listOrdersOptions } from '@/api/gen/@tanstack/react-query.gen'
import {
  type OrderFilters,
  OrdersDataGrid,
} from '@/components/blocks/data-grid-base-1/components/data-grid-view'
import { QueryError } from '@/components/query-error'
import { ORDER_STATUS_LABELS, RISK_TIER_LABELS } from '@/lib/labels'

type OrdersSearch = {
  tier?: RiskTier[]
  status?: OrderStatus[]
}

/** Keeps only known values; accepts a single value or a list. */
function pick<T extends string>(value: unknown, allowed: readonly T[]): T[] | undefined {
  const list = (Array.isArray(value) ? value : [value]).filter((v): v is T => allowed.includes(v as T))
  return list.length ? list : undefined
}

const TIERS = Object.keys(RISK_TIER_LABELS) as RiskTier[]
const STATUSES = Object.keys(ORDER_STATUS_LABELS) as OrderStatus[]

// One API page of the newest orders; search, filters, sorting and paging run in the browser.
// Cursor paging for larger inboxes comes with E7.2.
const LIST_QUERY = { sort: '-placed_at', limit: 100 } as const

export const Route = createFileRoute('/_shop/orders/')({
  staticData: { crumb: 'Đơn hàng' },
  validateSearch: (search: Record<string, unknown>): OrdersSearch => ({
    tier: pick(search.tier, TIERS),
    status: pick(search.status, STATUSES),
  }),
  loader: ({ context }) => context.queryClient.prefetchQuery(listOrdersOptions({ query: LIST_QUERY })),
  component: OrdersPage,
})

function OrdersPage() {
  const search = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })
  const { data, error, isPending, refetch } = useQuery(listOrdersOptions({ query: LIST_QUERY }))

  const filters: OrderFilters = { tiers: search.tier ?? [], statuses: search.status ?? [] }
  const setFilters = ({ tiers, statuses }: OrderFilters) =>
    navigate({
      search: { tier: tiers.length ? tiers : undefined, status: statuses.length ? statuses : undefined },
      replace: true,
    })

  if (error) return <QueryError error={error} />

  return (
    <OrdersDataGrid
      orders={data?.items ?? []}
      // The server's total can lag the page it returned (the mock's example says 0).
      total={Math.max(data?.total ?? 0, data?.items.length ?? 0)}
      isLoading={isPending}
      filters={filters}
      onFiltersChange={setFilters}
      onRefresh={() => void refetch()}
    />
  )
}
