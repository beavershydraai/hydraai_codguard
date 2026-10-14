import {
  type ColumnVisibilityState,
  type PaginationState,
  type SortingState,
  useTable,
} from '@tanstack/react-table'
import { FileDownIcon, FilterIcon, MoreHorizontalIcon, RefreshCwIcon, SearchIcon, XIcon } from 'lucide-react'
import { type ReactNode, useMemo, useState } from 'react'
import { toast } from 'sonner'

import type { OrderStatus, OrderSummary, RiskTier } from '@/api/gen'
import { Badge } from '@/components/reui/badge'
import { DataGrid as ReuiDataGrid, dataGridFeatures } from '@/components/reui/data-grid/data-grid'
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
} from '@/components/reui/frame'
import { OrderStatusBadge } from '@/components/order-status-badge'
import { TierBadge } from '@/components/tier-badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from '@/components/ui/input-group'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Separator } from '@/components/ui/separator'
import { TooltipProvider } from '@/components/ui/tooltip'
import { ordersToCsv } from '@/lib/orders-csv'
import { ORDER_STATUS_LABELS, RISK_TIER_LABELS } from '@/lib/labels'

import { columns } from './columns'

const TIER_ORDER = Object.keys(RISK_TIER_LABELS) as RiskTier[]
const STATUS_ORDER = Object.keys(ORDER_STATUS_LABELS) as OrderStatus[]

export type OrderFilters = {
  tiers: RiskTier[]
  statuses: OrderStatus[]
}

function orderSearchBlob(o: OrderSummary): string {
  return [o.id, o.external_id, o.buyer_name, o.buyer_phone].filter(Boolean).join(' ').toLowerCase()
}

function countBy<K extends string>(orders: OrderSummary[], key: (o: OrderSummary) => K | null | undefined) {
  return orders.reduce(
    (acc, o) => {
      const k = key(o)
      if (k) acc[k] = (acc[k] ?? 0) + 1
      return acc
    },
    {} as Partial<Record<K, number>>,
  )
}

// ── Filter popover (the block's status filter, reused for tier and status) ──

function FilterPopover<T extends string>({
  label,
  heading,
  options,
  selected,
  counts,
  renderOption,
  onChange,
}: {
  label: string
  heading: string
  options: T[]
  selected: T[]
  counts: Partial<Record<T, number>>
  renderOption: (value: T) => ReactNode
  onChange: (next: T[]) => void
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" aria-label={heading}>
          <FilterIcon aria-hidden="true" />
          {label}
          {selected.length > 0 && (
            <Badge size="sm" variant="info-outline">
              {selected.length}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="flex w-52 flex-col gap-2.5 p-3">
        <span className="text-xs font-medium text-muted-foreground">{heading}</span>
        {options.map((value) => (
          <div key={value} className="flex items-center gap-2.5">
            <Checkbox
              id={`filter-${label}-${value}`}
              checked={selected.includes(value)}
              onCheckedChange={(checked) =>
                onChange(checked === true ? [...selected, value] : selected.filter((v) => v !== value))
              }
            />
            <Label
              htmlFor={`filter-${label}-${value}`}
              className="flex min-w-0 flex-1 cursor-pointer items-center justify-between gap-2 font-normal"
            >
              {renderOption(value)}
              <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                {counts[value] ?? 0}
              </span>
            </Label>
          </div>
        ))}
      </PopoverContent>
    </Popover>
  )
}

// ── Toolbar ──

interface ToolbarProps {
  searchQuery: string
  onSearchChange: (v: string) => void
  filters: OrderFilters
  onFiltersChange: (filters: OrderFilters) => void
  tierCounts: Partial<Record<RiskTier, number>>
  statusCounts: Partial<Record<OrderStatus, number>>
  onRefresh: () => void
  onExport: () => void
}

function Toolbar({
  searchQuery,
  onSearchChange,
  filters,
  onFiltersChange,
  tierCounts,
  statusCounts,
  onRefresh,
  onExport,
}: ToolbarProps) {
  const hasActiveFilters =
    searchQuery.trim().length > 0 || filters.tiers.length > 0 || filters.statuses.length > 0

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <InputGroup className="w-full min-w-48 sm:w-56">
          <InputGroupAddon align="inline-start">
            <SearchIcon aria-hidden="true" />
          </InputGroupAddon>
          <InputGroupInput
            placeholder="Tìm mã đơn, tên, SĐT…"
            aria-label="Tìm đơn hàng"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
          />
          {searchQuery.length > 0 && (
            <InputGroupAddon align="inline-end">
              <InputGroupButton aria-label="Xóa tìm kiếm" size="icon-xs" onClick={() => onSearchChange('')}>
                <XIcon aria-hidden="true" />
              </InputGroupButton>
            </InputGroupAddon>
          )}
        </InputGroup>

        <FilterPopover
          label="Rủi ro"
          heading="Lọc theo mức rủi ro"
          options={TIER_ORDER}
          selected={filters.tiers}
          counts={tierCounts}
          renderOption={(tier) => <TierBadge tier={tier} />}
          onChange={(tiers) => onFiltersChange({ ...filters, tiers })}
        />

        <FilterPopover
          label="Trạng thái"
          heading="Lọc theo trạng thái"
          options={STATUS_ORDER}
          selected={filters.statuses}
          counts={statusCounts}
          renderOption={(status) => <OrderStatusBadge status={status} />}
          onChange={(statuses) => onFiltersChange({ ...filters, statuses })}
        />

        {hasActiveFilters && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="text-muted-foreground"
            onClick={() => {
              onSearchChange('')
              onFiltersChange({ tiers: [], statuses: [] })
            }}
          >
            Xóa bộ lọc
          </Button>
        )}
      </div>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" aria-label="Thao tác với bảng">
            <MoreHorizontalIcon aria-hidden="true" />
            Thao tác
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-40">
          <DropdownMenuGroup>
            <DropdownMenuItem onClick={onExport}>
              <FileDownIcon aria-hidden="true" />
              Xuất CSV
            </DropdownMenuItem>
            <DropdownMenuItem onClick={onRefresh}>
              <RefreshCwIcon aria-hidden="true" />
              Làm mới
            </DropdownMenuItem>
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}

// ── Main component ──

export function OrdersDataGrid({
  orders,
  total,
  isLoading,
  filters,
  onFiltersChange,
  onRefresh,
}: {
  orders: OrderSummary[]
  /** Orders matching on the server; `orders` holds the newest page of them. */
  total: number
  isLoading: boolean
  filters: OrderFilters
  onFiltersChange: (filters: OrderFilters) => void
  onRefresh: () => void
}) {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 })
  const [sorting, setSorting] = useState<SortingState>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [columnOrder, setColumnOrder] = useState<string[]>(columns.map((c) => c.id as string))
  const [columnVisibility, setColumnVisibility] = useState<ColumnVisibilityState>({})

  const tierCounts = useMemo(() => countBy(orders, (o) => o.tier), [orders])
  const statusCounts = useMemo(() => countBy(orders, (o) => o.status), [orders])

  const filteredData = useMemo(() => {
    const searchLower = searchQuery.trim().toLowerCase()
    return orders.filter(
      (o) =>
        (!filters.tiers.length || (o.tier != null && filters.tiers.includes(o.tier))) &&
        (!filters.statuses.length || filters.statuses.includes(o.status)) &&
        (!searchLower || orderSearchBlob(o).includes(searchLower)),
    )
  }, [orders, searchQuery, filters])

  // Back to the first page whenever the search or a filter changes (also from the sidebar).
  const filterKey = JSON.stringify([searchQuery, filters])
  const [lastFilterKey, setLastFilterKey] = useState(filterKey)
  if (filterKey !== lastFilterKey) {
    setLastFilterKey(filterKey)
    setPagination((current) => ({ ...current, pageIndex: 0 }))
  }

  const table = useTable({
    features: dataGridFeatures,
    columns,
    data: filteredData,
    pageCount: Math.ceil(filteredData.length / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting, columnOrder, columnVisibility },
    autoResetPageIndex: false,
    onColumnOrderChange: setColumnOrder,
    onColumnVisibilityChange: setColumnVisibility,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
  })

  const handleExport = () => {
    const blob = new Blob([ordersToCsv(filteredData)], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `don-hang-${new Date().toISOString().slice(0, 10)}.csv`
    link.click()
    URL.revokeObjectURL(url)
    toast.success('Đã xuất CSV', { description: `${filteredData.length} đơn` })
  }

  return (
    <TooltipProvider delayDuration={200}>
      <ReuiDataGrid
        table={table}
        recordCount={filteredData.length}
        isLoading={isLoading}
        emptyMessage={
          orders.length === 0
            ? 'Chưa có đơn nào.'
            : 'Không có đơn khớp với tìm kiếm hoặc bộ lọc. Xóa bộ lọc để xem tất cả.'
        }
        tableLayout={{
          columnsPinnable: true,
          columnsResizable: true,
          columnsMovable: true,
          columnsVisibility: true,
          dense: true,
        }}
      >
        <Frame variant="default" spacing="sm" className="w-full">
          <FrameHeader className="flex-row items-center justify-between gap-3">
            <div className="flex flex-col gap-0.5">
              <FrameTitle className="text-balance">Đơn hàng</FrameTitle>
              <FrameDescription className="text-xs text-pretty">
                {filteredData.length} / {total} đơn đã chấm điểm rủi ro bom hàng
              </FrameDescription>
            </div>
          </FrameHeader>
          <FramePanel className="bg-card p-0! shadow-none!">
            <div className="px-4 py-3">
              <Toolbar
                searchQuery={searchQuery}
                onSearchChange={setSearchQuery}
                filters={filters}
                onFiltersChange={onFiltersChange}
                tierCounts={tierCounts}
                statusCounts={statusCounts}
                onRefresh={onRefresh}
                onExport={handleExport}
              />
            </div>
            <Separator />
            <DataGridScrollArea>
              <DataGridTable />
            </DataGridScrollArea>
          </FramePanel>
          <FrameFooter>
            <DataGridPagination
              info="{from} - {to} trên {count} đơn"
              rowsPerPageLabel="Số đơn mỗi trang"
              previousPageLabel="Trang trước"
              nextPageLabel="Trang sau"
            />
          </FrameFooter>
        </Frame>
      </ReuiDataGrid>
    </TooltipProvider>
  )
}
