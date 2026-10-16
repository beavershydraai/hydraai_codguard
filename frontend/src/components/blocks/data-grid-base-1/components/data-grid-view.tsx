import { type ColumnVisibilityState, type SortingState, useTable } from '@tanstack/react-table'
import { FileDownIcon, FilterIcon, MoreHorizontalIcon, RefreshCwIcon, SearchIcon, XIcon } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { toast } from 'sonner'

import type { ListOrdersData, OrderStatus, OrderSummary, RiskTier } from '@/api/gen'
import { Badge } from '@/components/reui/badge'
import { DataGrid as ReuiDataGrid, dataGridFeatures } from '@/components/reui/data-grid/data-grid'
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
import { Spinner } from '@/components/ui/spinner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { ordersToCsv } from '@/lib/orders-csv'
import { BRANCH_LABELS, ORDER_STATUS_LABELS, RISK_TIER_LABELS } from '@/lib/labels'

import { columns } from './columns'

// The inbox is served page by page by the API (E7.2): filters, search and sort run on the server,
// and "Load more" fetches the next page. Nothing is filtered or sorted in the browser.

const TIER_ORDER = Object.keys(RISK_TIER_LABELS) as RiskTier[]
const STATUS_ORDER = Object.keys(ORDER_STATUS_LABELS) as OrderStatus[]
const BRANCH_ORDER = Object.keys(BRANCH_LABELS)

export type OrderFilters = {
  tiers: RiskTier[]
  statuses: OrderStatus[]
  branches: string[]
}
export type OrderSort = NonNullable<NonNullable<ListOrdersData['query']>['sort']>

/** The table's sort state for an API sort, and back. Only these columns sort on the server. */
function toSorting(sort: OrderSort): SortingState {
  return [{ id: sort.replace(/^-/, ''), desc: sort.startsWith('-') }]
}
function toSort(sorting: SortingState): OrderSort {
  const first = sorting[0]
  if (first?.id === 'placed_at') return first.desc ? '-placed_at' : 'placed_at'
  if (first?.id === 'risk_score') return '-risk_score'
  if (first?.id === 'cod_amount_vnd') return '-cod_amount_vnd'
  return '-placed_at'
}

// ── Filter popover (the block's status filter, reused for tier and status) ──

function FilterPopover<T extends string>({
  label,
  heading,
  options,
  selected,
  renderOption,
  onChange,
}: {
  label: string
  heading: string
  options: T[]
  selected: T[]
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
            </Label>
          </div>
        ))}
      </PopoverContent>
    </Popover>
  )
}

// ── Toolbar ──

interface ToolbarProps {
  search: string
  onSearchChange: (v: string) => void
  filters: OrderFilters
  onFiltersChange: (filters: OrderFilters) => void
  onRefresh: () => void
  onExport: () => void
}

function Toolbar({ search, onSearchChange, filters, onFiltersChange, onRefresh, onExport }: ToolbarProps) {
  // Searched on Enter: the server matches exact values, not as you type.
  const [draft, setDraft] = useState(search)
  const hasActiveFilters =
    search.length > 0 ||
    filters.tiers.length > 0 ||
    filters.statuses.length > 0 ||
    filters.branches.length > 0

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <form
          onSubmit={(event) => {
            event.preventDefault()
            onSearchChange(draft.trim())
          }}
        >
          <InputGroup className="w-full min-w-48 sm:w-72">
            <InputGroupAddon align="inline-start">
              <SearchIcon aria-hidden="true" />
            </InputGroupAddon>
            <InputGroupInput
              placeholder="Order ID, shop order ID or full phone"
              aria-label="Search orders by exact order ID, shop order ID or full phone number"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
            {draft.length > 0 && (
              <InputGroupAddon align="inline-end">
                <InputGroupButton
                  aria-label="Clear search"
                  size="icon-xs"
                  onClick={() => {
                    setDraft('')
                    onSearchChange('')
                  }}
                >
                  <XIcon aria-hidden="true" />
                </InputGroupButton>
              </InputGroupAddon>
            )}
          </InputGroup>
        </form>

        <FilterPopover
          label="Branch"
          heading="Filter by branch"
          options={BRANCH_ORDER}
          selected={filters.branches}
          renderOption={(branch) => <span className="truncate text-sm">{BRANCH_LABELS[branch]}</span>}
          onChange={(branches) => onFiltersChange({ ...filters, branches })}
        />

        <FilterPopover
          label="Risk"
          heading="Filter by risk tier"
          options={TIER_ORDER}
          selected={filters.tiers}
          renderOption={(tier) => <TierBadge tier={tier} />}
          onChange={(tiers) => onFiltersChange({ ...filters, tiers })}
        />

        <FilterPopover
          label="Status"
          heading="Filter by status"
          options={STATUS_ORDER}
          selected={filters.statuses}
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
              setDraft('')
              onSearchChange('')
              onFiltersChange({ tiers: [], statuses: [], branches: [] })
            }}
          >
            Clear filters
          </Button>
        )}
      </div>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" aria-label="Table actions">
            <MoreHorizontalIcon aria-hidden="true" />
            Actions
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          <DropdownMenuGroup>
            <DropdownMenuItem onClick={onExport}>
              <FileDownIcon aria-hidden="true" />
              Export loaded orders
            </DropdownMenuItem>
            <DropdownMenuItem onClick={onRefresh}>
              <RefreshCwIcon aria-hidden="true" />
              Refresh
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
  search,
  onSearchChange,
  sort,
  onSortChange,
  hasMore,
  isLoadingMore,
  onLoadMore,
  onRefresh,
  headerActions,
}: {
  /** The pages loaded so far, in the server's order. */
  orders: OrderSummary[]
  /** Orders matching the filters on the server. */
  total: number
  isLoading: boolean
  filters: OrderFilters
  onFiltersChange: (filters: OrderFilters) => void
  search: string
  onSearchChange: (search: string) => void
  sort: OrderSort
  onSortChange: (sort: OrderSort) => void
  hasMore: boolean
  isLoadingMore: boolean
  onLoadMore: () => void
  onRefresh: () => void
  /** Buttons in the frame header, like the block's "Add customer" button. */
  headerActions?: ReactNode
}) {
  const [columnOrder, setColumnOrder] = useState<string[]>(columns.map((c) => c.id as string))
  const [columnVisibility, setColumnVisibility] = useState<ColumnVisibilityState>({})
  const sorting = toSorting(sort)

  const table = useTable({
    features: dataGridFeatures,
    columns,
    data: orders,
    getRowId: (row) => row.id,
    // Every loaded order on one page: the server sorts and pages.
    state: {
      pagination: { pageIndex: 0, pageSize: Math.max(orders.length, 1) },
      sorting,
      columnOrder,
      columnVisibility,
    },
    manualSorting: true,
    manualPagination: true,
    pageCount: 1,
    onColumnOrderChange: setColumnOrder,
    onColumnVisibilityChange: setColumnVisibility,
    onSortingChange: (updater) =>
      onSortChange(toSort(typeof updater === 'function' ? updater(sorting) : updater)),
  })

  const handleExport = () => {
    const blob = new Blob([ordersToCsv(orders)], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `orders-${new Date().toISOString().slice(0, 10)}.csv`
    link.click()
    URL.revokeObjectURL(url)
    toast.success('CSV exported', { description: `${orders.length} loaded orders` })
  }

  const filtered =
    search.length > 0 ||
    filters.tiers.length > 0 ||
    filters.statuses.length > 0 ||
    filters.branches.length > 0

  return (
    <TooltipProvider delayDuration={200}>
      <ReuiDataGrid
        table={table}
        recordCount={orders.length}
        isLoading={isLoading}
        emptyMessage={
          filtered
            ? 'No orders match the search or filters. Clear the filters to see all orders.'
            : 'No orders yet.'
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
              <FrameTitle className="text-balance">Orders</FrameTitle>
              <FrameDescription className="text-xs text-pretty">
                {total} orders{filtered ? ' match' : ''}, scored for failed-delivery risk
              </FrameDescription>
            </div>
            {headerActions && <div className="flex flex-wrap items-center gap-2">{headerActions}</div>}
          </FrameHeader>
          <FramePanel className="bg-card p-0! shadow-none!">
            <div className="px-4 py-3">
              <Toolbar
                key={search}
                search={search}
                onSearchChange={onSearchChange}
                filters={filters}
                onFiltersChange={onFiltersChange}
                onRefresh={onRefresh}
                onExport={handleExport}
              />
            </div>
            <Separator />
            <DataGridScrollArea>
              <DataGridTable />
            </DataGridScrollArea>
          </FramePanel>
          <FrameFooter className="flex-row items-center justify-between gap-3">
            <span className="text-xs text-muted-foreground tabular-nums">
              Showing {orders.length} of {total}
            </span>
            {hasMore && (
              <Button variant="outline" size="sm" onClick={onLoadMore} disabled={isLoadingMore}>
                {isLoadingMore && <Spinner data-icon="inline-start" />}
                Load more
              </Button>
            )}
          </FrameFooter>
        </Frame>
      </ReuiDataGrid>
    </TooltipProvider>
  )
}
