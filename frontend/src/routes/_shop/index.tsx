import { useQuery } from '@tanstack/react-query'
import { createFileRoute, useNavigate } from '@tanstack/react-router'

import { getDashboardSummaryOptions } from '@/api/gen/@tanstack/react-query.gen'
import { type Period, PERIODS } from '@/components/blocks/dashboard-1/components/data'
import { RoiDashboard } from '@/components/blocks/dashboard-1/components/roi-dashboard'
import { QueryError } from '@/components/query-error'

type DashboardSearch = { period?: Period }

/** The last `days` days in Vietnam time, as the inclusive dates the API expects. */
function range(days: number): { from: string; to: string } {
  const toDate = (ms: number) => new Date(ms + 7 * 3_600_000).toISOString().slice(0, 10)
  const now = Date.now()
  return { from: toDate(now - (days - 1) * 86_400_000), to: toDate(now) }
}

export const Route = createFileRoute('/_shop/')({
  staticData: { crumb: 'Overview' },
  validateSearch: (search: Record<string, unknown>): DashboardSearch => ({
    period: PERIODS.some((p) => p.value === search.period) ? (search.period as Period) : undefined,
  }),
  component: DashboardPage,
})

function DashboardPage() {
  const { period = '30' } = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })
  const { data, error, isPending } = useQuery(getDashboardSummaryOptions({ query: range(Number(period)) }))

  if (error) return <QueryError error={error} />
  return (
    <RoiDashboard
      summary={data}
      isLoading={isPending}
      period={period}
      onPeriodChange={(next) =>
        navigate({ search: { period: next === '30' ? undefined : next }, replace: true })
      }
    />
  )
}
