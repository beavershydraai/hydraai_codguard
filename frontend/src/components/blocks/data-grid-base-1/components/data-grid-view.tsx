import { type ColumnVisibilityState, type SortingState, useTable } from '@tanstack/react-table'
import { FileDownIcon, MoreHorizontalIcon, RefreshCwIcon, SearchIcon, XIcon } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { toast } from 'sonner'

import type { ListOrdersData, OrderSummary } from '@/api/gen'
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
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from '@/components/ui/input-group'
import { Separator } from '@/components/ui/separator'
import { Spinner } from '@/components/ui/spinner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { ordersToCsv } from '@/lib/orders-csv'

import { columns } from './columns'
import { OrderFilterBar, type OrderFilters } from './order-filters'

export type { OrderFilters }

// The inbox is served page by page by the API (E7.2): filters, search and sort run on the server,
// and each page holds 50 orders, with previous and next. Nothing is filtered or sorted here.

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
    filters.branches.length > 0 ||
    !!filters.placedFrom

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

        <OrderFilterBar filters={filters} onFiltersChange={onFiltersChange} />

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
        <DropdownMenuTrigger render={<Button variant="outline" aria-label="Table actions" />}>
          <MoreHorizontalIcon aria-hidden="true" />
          Actions
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          <DropdownMenuGroup>
            <DropdownMenuItem onClick={onExport}>
              <FileDownIcon aria-hidden="true" />
              Export this page
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
  page,
  pageSize,
  isFetching,
  onPrevious,
  onNext,
  onRefresh,
  headerActions,
}: {
  /** The page shown, in the server's order. */
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
  /** 0-based index of the page shown. */
  page: number
  pageSize: number
  isFetching: boolean
  /** Unset on the first page. */
  onPrevious?: () => void
  /** Unset on the last page. */
  onNext?: () => void
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
    // The server's page is the table's only page: the server sorts and pages.
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
    toast.success('CSV exported', { description: `${orders.length} orders on this page` })
  }

  const filtered =
    search.length > 0 ||
    filters.tiers.length > 0 ||
    filters.statuses.length > 0 ||
    filters.branches.length > 0 ||
    !!filters.placedFrom

  return (
    <TooltipProvider delay={200}>
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
              {orders.length > 0
                ? `${page * pageSize + 1}–${page * pageSize + orders.length} of ${total}`
                : `0 of ${total}`}
            </span>
            <div className="flex items-center gap-2">
              {isFetching && <Spinner aria-label="Loading" />}
              <span className="text-xs text-muted-foreground tabular-nums">
                Page {page + 1} of {Math.max(1, Math.ceil(total / pageSize))}
              </span>
              <Button variant="outline" size="sm" onClick={onPrevious} disabled={!onPrevious || isFetching}>
                Previous
              </Button>
              <Button variant="outline" size="sm" onClick={onNext} disabled={!onNext || isFetching}>
                Next
              </Button>
            </div>
          </FrameFooter>
        </Frame>
      </ReuiDataGrid>
    </TooltipProvider>
  )
}
