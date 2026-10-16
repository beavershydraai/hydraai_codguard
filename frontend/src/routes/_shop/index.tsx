import { useQuery } from '@tanstack/react-query'
import { createFileRoute, useNavigate } from '@tanstack/react-router'

import { getDashboardSummaryOptions } from '@/api/gen/@tanstack/react-query.gen'
import { type Period, PERIODS } from '@/components/blocks/dashboard-1/components/data'
import { RoiDashboard } from '@/components/blocks/dashboard-1/components/roi-dashboard'
import { QueryError } from '@/components/query-error'

type DashboardSearch = { period?: Period; country?: Country }
type Country = 'VN' | 'SG' | 'PH'

const UTC_OFFSET_HOURS: Record<Country, number> = { VN: 7, SG: 8, PH: 8 }

/** The last `days` days in the country's local time, as the inclusive dates the API expects. */
function range(days: number, country: Country): { from: string; to: string; country: Country } {
  const toDate = (ms: number) =>
    new Date(ms + UTC_OFFSET_HOURS[country] * 3_600_000).toISOString().slice(0, 10)
  const now = Date.now()
  return { from: toDate(now - (days - 1) * 86_400_000), to: toDate(now), country }
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

  if (error) return <QueryError error={error} />
  return (
    <RoiDashboard
      summary={data}
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
