import { useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'

import { getBacktestOptions } from '@/api/gen/@tanstack/react-query.gen'
import { BacktestView } from '@/components/blocks/dashboard-1/components/backtest-view'
import { QueryError } from '@/components/query-error'

export const Route = createFileRoute('/_shop/backtest')({
  staticData: { crumb: 'Backtest' },
  component: BacktestPage,
})

function BacktestPage() {
  const { data, error, isPending } = useQuery({ ...getBacktestOptions(), staleTime: 5 * 60_000 })
  if (error) return <QueryError error={error} />
  return <BacktestView result={data} isLoading={isPending} />
}
