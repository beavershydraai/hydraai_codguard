import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { PlusIcon, TruckIcon, UploadIcon } from 'lucide-react'
import { useState } from 'react'

import { importDeliveryOutcomes, importOrders, type OrderStatus, type RiskTier } from '@/api/gen'
import { listOrdersOptions } from '@/api/gen/@tanstack/react-query.gen'
import {
  type OrderFilters,
  OrdersDataGrid,
} from '@/components/blocks/data-grid-base-1/components/data-grid-view'
import { CreateOrderSheet } from '@/components/orders/create-order-sheet'
import { CsvImportDialog } from '@/components/orders/csv-import-dialog'
import { QueryError } from '@/components/query-error'
import { Button } from '@/components/ui/button'
import { invalidate } from '@/lib/api'
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
    'Áo thun cotton',
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
  const queryClient = useQueryClient()
  const [panel, setPanel] = useState<'create' | 'import' | 'delivery' | null>(null)
  const close = (open: boolean) => !open && setPanel(null)

  const filters: OrderFilters = { tiers: search.tier ?? [], statuses: search.status ?? [] }
  const setFilters = ({ tiers, statuses }: OrderFilters) =>
    navigate({
      search: { tier: tiers.length ? tiers : undefined, status: statuses.length ? statuses : undefined },
      replace: true,
    })

  if (error) return <QueryError error={error} />

  return (
    <>
      <OrdersDataGrid
        headerActions={
          <>
            <Button variant="outline" size="sm" onClick={() => setPanel('delivery')}>
              <TruckIcon aria-hidden="true" />
              Nhập kết quả giao
            </Button>
            <Button variant="outline" size="sm" onClick={() => setPanel('import')}>
              <UploadIcon aria-hidden="true" />
              Nhập đơn
            </Button>
            <Button size="sm" onClick={() => setPanel('create')}>
              <PlusIcon aria-hidden="true" />
              Tạo đơn
            </Button>
          </>
        }
        orders={data?.items ?? []}
        // The server's total can lag the page it returned (the mock's example says 0).
        total={Math.max(data?.total ?? 0, data?.items.length ?? 0)}
        isLoading={isPending}
        filters={filters}
        onFiltersChange={setFilters}
        onRefresh={() => void refetch()}
      />
      <CreateOrderSheet open={panel === 'create'} onOpenChange={close} />
      <CsvImportDialog
        open={panel === 'import'}
        onOpenChange={close}
        title="Nhập đơn từ file"
        description="Mỗi dòng một đơn. Đơn trùng mã đơn của shop được bỏ qua; đơn mới được chấm điểm ngay."
        templateName="mau-nhap-don.csv"
        template={ORDER_TEMPLATE}
        onImport={async (file) => {
          const { data } = await importOrders({ body: { file }, throwOnError: true })
          void invalidate(queryClient, 'listOrders', 'getDashboardSummary')
          return {
            counts: [
              ['Số dòng', data.received],
              ['Đã nhập', data.imported],
              ['Trùng', data.duplicates],
              ['Lỗi', data.rejected?.length ?? 0],
            ],
            rejected: data.rejected ?? [],
          }
        }}
      />
      <CsvImportDialog
        open={panel === 'delivery'}
        onOpenChange={close}
        title="Nhập kết quả giao hàng"
        description="Kết quả từ GHN, GHTK… cập nhật trạng thái đơn và lịch sử SĐT. Chỉ từ chối nhận và không liên lạc được mới tính là lỗi của người mua."
        templateName="mau-ket-qua-giao.csv"
        template={DELIVERY_TEMPLATE}
        onImport={async (file) => {
          const { data } = await importDeliveryOutcomes({ body: { file }, throwOnError: true })
          void invalidate(queryClient, 'listOrders', 'getOrder', 'getDashboardSummary')
          return {
            counts: [
              ['Số dòng', data.received],
              ['Đã cập nhật', data.applied],
              ['Không rõ đơn', data.unknown_orders],
              ['Lỗi', data.rejected?.length ?? 0],
            ],
            rejected: data.rejected ?? [],
          }
        }}
      />
    </>
  )
}
