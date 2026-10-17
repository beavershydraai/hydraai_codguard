import { useQuery } from '@tanstack/react-query'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useEffect } from 'react'

import {
  getDashboardSummaryOptions,
  getShopOptions,
  listOrdersOptions,
} from '@/api/gen/@tanstack/react-query.gen'
import { type Period, PERIODS } from '@/components/blocks/dashboard-1/components/data'
import { RoiDashboard } from '@/components/blocks/dashboard-1/components/roi-dashboard'
import { useOnboardingStore } from '@/stores/onboarding'

type DashboardSearch = { period?: Period; country?: Country }
type Country = 'VN' | 'SG' | 'PH'

const UTC_OFFSET_HOURS: Record<Country, number> = { VN: 7, SG: 8, PH: 8 }

/**
 * The last `days` days in the country's local time, as the inclusive dates the API expects;
 * `before` days earlier for the period to compare with.
 */
function range(days: number, country: Country, before = 0): { from: string; to: string; country: Country } {
  const toDate = (ms: number) =>
    new Date(ms + UTC_OFFSET_HOURS[country] * 3_600_000).toISOString().slice(0, 10)
  const end = Date.now() - before * 86_400_000
  return { from: toDate(end - (days - 1) * 86_400_000), to: toDate(end), country }
}

export const Route = createFileRoute('/_shop/')({
  staticData: { crumb: 'Overview' },
  validateSearch: (search: Record<string, unknown>): DashboardSearch => ({
    period: PERIODS.some((p) => p.value === search.period) ? (search.period as Period) : undefined,
    country: search.country === 'SG' || search.country === 'PH' ? search.country : undefined,
  }),
  component: DashboardPage,
})

function DashboardPage() {
  const { period = '30', country = 'VN' } = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })
  const { data, error, isPending } = useQuery({
    ...getDashboardSummaryOptions({ query: range(Number(period), country) }),
    staleTime: 60_000,
  })
  // The period before, for the trend on each figure.
  const previous = useQuery({
    ...getDashboardSummaryOptions({ query: range(Number(period), country, Number(period)) }),
    staleTime: 5 * 60_000,
  })
  // A shop with no order at all has just signed up: set it up first.
  const shop = useQuery(getShopOptions())
  const firstOrder = useQuery(listOrdersOptions({ query: { limit: 1 } }))
  const done = useOnboardingStore((s) => (shop.data ? s.done.includes(shop.data.id) : true))
  const empty = !done && firstOrder.data?.total === 0
  useEffect(() => {
    if (empty) void navigate({ to: '/onboarding' })
  }, [empty, navigate])

  // An error keeps the page: its figures and charts show empty, with the error above them.
  return (
    <RoiDashboard
      summary={data}
      error={error}
      previous={previous.data}
      isLoading={isPending}
      period={period}
      onPeriodChange={(next) =>
        navigate({ search: (s) => ({ ...s, period: next === '30' ? undefined : next }), replace: true })
      }
      country={country}
      onCountryChange={(next) =>
        navigate({
          search: (s) => ({ ...s, country: next === 'VN' ? undefined : (next as Country) }),
          replace: true,
        })
      }
    />
  )
}
