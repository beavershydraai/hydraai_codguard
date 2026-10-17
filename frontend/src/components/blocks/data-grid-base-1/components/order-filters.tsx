import { subDays } from 'date-fns'
import { CalendarRangeIcon, ListChecksIcon, ShieldAlertIcon, StoreIcon } from 'lucide-react'
import { useState } from 'react'

import type { OrderStatus, RiskTier } from '@/api/gen'
import { Filters } from '@/components/reui/filters/filters'
import {
  type FilterDateValue,
  formatFilterDate,
  resolveFilterDate,
  toFilterDateValue,
} from '@/components/reui/filters/filters-date'
import {
  createFilterQuery,
  createFilterRule,
  flattenFilterConditions,
} from '@/components/reui/filters/filters-query'
import type {
  FilterEditorProps,
  FilterField,
  FilterOperator,
  FilterQuery,
} from '@/components/reui/filters/filters-types'
import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { BRANCH_LABELS, ORDER_STATUS_LABELS } from '@/lib/labels'
import { cn } from '@/lib/utils'

import { TIER_SHORTCUTS } from '../../app-shell-1/components/data'

// The order inbox's filter bar: ReUI Filters (c-filters-7) with a date range editor (c-filters-5).
// The server filters (E7.2) on any of some branches, tiers and statuses and on a placing-time
// range, so each field offers only the conditions the API can answer.

export type OrderFilters = {
  tiers: RiskTier[]
  statuses: OrderStatus[]
  branches: string[]
  /** Placed on or after this day, `yyyy-MM-dd`. */
  placedFrom?: string
  /** Placed on or before this day, `yyyy-MM-dd`. */
  placedTo?: string
}

type DateRange = [FilterDateValue, FilterDateValue]

const ANY_OF: FilterOperator[] = [{ value: 'is_any_of', label: 'is any of', arity: 'many' }]
const BETWEEN: FilterOperator[] = [{ value: 'between', label: 'is between', arity: 'range' }]

const DAY_GRID = 'p-0 [--cell-size:--spacing(7)] [&_.rdp-month]:gap-2 [&_tbody_tr]:mt-1'

const today = () => new Date()
const RANGE_PRESETS: [string, () => DateRange][] = [
  ['Today', () => [toFilterDateValue(today()), toFilterDateValue(today())]],
  ['Last 7 days', () => [toFilterDateValue(subDays(today(), 6)), toFilterDateValue(today())]],
  ['Last 30 days', () => [toFilterDateValue(subDays(today(), 29)), toFilterDateValue(today())]],
]

function PlacedRangeEditor({
  value,
  onValueChange,
  commit,
  cancel,
  autoFocusProps,
  labels,
}: FilterEditorProps) {
  const range = Array.isArray(value) ? (value as DateRange) : undefined
  const from = resolveFilterDate(range?.[0]) ?? undefined
  const to = resolveFilterDate(range?.[1]) ?? undefined

  return (
    <div className="flex flex-col gap-2 p-2">
      <div className="grid grid-cols-3 gap-1.5">
        {RANGE_PRESETS.map(([label, preset], index) => (
          <Button
            key={label}
            {...(index === 0 ? autoFocusProps : {})}
            variant="outline"
            size="sm"
            onClick={() => commit(preset())}
          >
            {label}
          </Button>
        ))}
      </div>
      <Calendar
        mode="range"
        className={DAY_GRID}
        selected={{ from, to }}
        defaultMonth={from}
        disabled={{ after: today() }}
        onSelect={(next) => {
          if (!next?.from) return
          onValueChange([toFilterDateValue(next.from), toFilterDateValue(next.to ?? next.from)])
        }}
      />
      {/* A range takes two clicks, so it is applied by hand rather than on the first one. */}
      <div className="-mx-2 flex items-center justify-end gap-1.5 border-t px-2 pt-2">
        <Button variant="ghost" size="sm" onClick={cancel}>
          {labels.discard}
        </Button>
        <Button size="sm" disabled={!range} onClick={() => commit()}>
          {labels.apply}
        </Button>
      </div>
    </div>
  )
}

const rangeText = (value: unknown, valueRange: (from: string, to: string) => string) =>
  Array.isArray(value)
    ? valueRange(formatFilterDate(value[0] as FilterDateValue), formatFilterDate(value[1] as FilterDateValue))
    : 'Select dates'

const fields: FilterField[] = [
  {
    id: 'branch',
    label: 'Branch',
    type: 'select',
    operators: ANY_OF,
    defaultOperator: 'is_any_of',
    searchable: false,
    options: Object.entries(BRANCH_LABELS).map(([value, label]) => ({ value, label })),
    icon: <StoreIcon />,
  },
  {
    id: 'tier',
    label: 'Risk',
    type: 'select',
    operators: ANY_OF,
    defaultOperator: 'is_any_of',
    searchable: false,
    // The sidebar's tier dots, so a chip reads "Risk is any of • High" rather than "High High".
    options: TIER_SHORTCUTS.map(({ tier, name, color }) => ({
      value: tier,
      label: name,
      icon: <span className={cn('size-2 shrink-0 rounded-full', color)} />,
    })),
    icon: <ShieldAlertIcon />,
  },
  {
    id: 'status',
    label: 'Status',
    type: 'select',
    operators: ANY_OF,
    defaultOperator: 'is_any_of',
    searchable: false,
    options: (Object.keys(ORDER_STATUS_LABELS) as OrderStatus[]).map((status) => ({
      value: status,
      label: ORDER_STATUS_LABELS[status],
    })),
    icon: <ListChecksIcon />,
  },
  {
    id: 'placed',
    label: 'Placed',
    operators: BETWEEN,
    defaultOperator: 'between',
    editor: PlacedRangeEditor,
    renderValue: ({ value, labels }) => rangeText(value, labels.valueRange),
    valueText: ({ value, labels }) => rangeText(value, labels.valueRange),
    icon: <CalendarRangeIcon />,
  },
]

/** The filters a query asks for. A field used twice keeps every value picked in either rule. */
function toOrderFilters(query: FilterQuery): OrderFilters {
  const filters: OrderFilters = { tiers: [], statuses: [], branches: [] }
  for (const rule of flattenFilterConditions(query)) {
    const field = rule.path[0]
    if (field === 'placed') {
      const [from, to] = (rule.values as DateRange | undefined) ?? []
      filters.placedFrom = from?.date
      filters.placedTo = to?.date
      continue
    }
    const values = (rule.values ?? []) as string[]
    if (field === 'branch') filters.branches.push(...values)
    if (field === 'tier') filters.tiers.push(...(values as RiskTier[]))
    if (field === 'status') filters.statuses.push(...(values as OrderStatus[]))
  }
  return {
    ...filters,
    branches: [...new Set(filters.branches)],
    tiers: [...new Set(filters.tiers)],
    statuses: [...new Set(filters.statuses)],
  }
}

function toQuery(filters: OrderFilters): FilterQuery {
  const rule = (path: string, value: unknown) =>
    createFilterRule({
      id: path,
      path: [path],
      operator: path === 'placed' ? 'between' : 'is_any_of',
      value,
    })
  return createFilterQuery([
    ...(filters.branches.length ? [rule('branch', filters.branches)] : []),
    ...(filters.tiers.length ? [rule('tier', filters.tiers)] : []),
    ...(filters.statuses.length ? [rule('status', filters.statuses)] : []),
    ...(filters.placedFrom && filters.placedTo
      ? [rule('placed', [{ date: filters.placedFrom }, { date: filters.placedTo }])]
      : []),
  ])
}

const filtersKey = (f: OrderFilters) =>
  JSON.stringify([
    [...f.branches].sort(),
    [...f.tiers].sort(),
    [...f.statuses].sort(),
    f.placedFrom ?? null,
    f.placedTo ?? null,
  ])
const sameFilters = (a: OrderFilters, b: OrderFilters) => filtersKey(a) === filtersKey(b)

export function OrderFilterBar({
  filters,
  onFiltersChange,
}: {
  filters: OrderFilters
  onFiltersChange: (filters: OrderFilters) => void
}) {
  // The bar keeps its own query, so a rule still being built (no value yet) stays on screen.
  // When the filters change elsewhere (the sidebar's tier links, Clear filters), it starts over
  // from them.
  const [query, setQuery] = useState(() => toQuery(filters))
  const [shown, setShown] = useState(filters)
  if (!sameFilters(filters, shown)) {
    setShown(filters)
    if (!sameFilters(filters, toOrderFilters(query))) setQuery(toQuery(filters))
  }

  return (
    <Filters
      fields={fields}
      query={query}
      onQueryChange={(next) => {
        setQuery(next)
        const nextFilters = toOrderFilters(next)
        if (!sameFilters(nextFilters, filters)) onFiltersChange(nextFilters)
      }}
    />
  )
}
