import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import { toast } from 'sonner'

import {
  getBacktestOptions,
  getMeOptions,
  getModelHealthOptions,
  updateModelsMutation,
} from '@/api/gen/@tanstack/react-query.gen'
import { BacktestView } from '@/components/blocks/dashboard-1/components/backtest-view'
import { ModelHealthCard } from '@/components/blocks/dashboard-1/components/model-health'
import { QueryError } from '@/components/query-error'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { invalidate, problemMessage } from '@/lib/api'

export const Route = createFileRoute('/_shop/backtest')({
  staticData: { crumb: 'Risk model' },
  component: BacktestPage,
})

// One risk model per country, so one backtest per country.
const COUNTRIES = [
  { value: 'VN', label: 'Vietnam' },
  { value: 'SG', label: 'Singapore' },
  { value: 'PH', label: 'Philippines' },
] as const
type Country = (typeof COUNTRIES)[number]['value']

function BacktestPage() {
  const queryClient = useQueryClient()
  const [country, setCountry] = useState<Country>('VN')
  const { data, error, isPending } = useQuery({
    ...getBacktestOptions({ query: { country } }),
    staleTime: 5 * 60_000,
  })
  const { data: me } = useQuery(getMeOptions())
  const { data: models } = useQuery({
    ...getModelHealthOptions(),
    // While an update runs, check every 15 s so the new model and backtest show up on their own.
    refetchInterval: (q) => (q.state.data?.some((m) => m.updating) ? 15_000 : false),
  })
  const health = models?.find((m) => m.country === country)
  const wasUpdating = models?.some((m) => m.updating)
  const [lastUpdating, setLastUpdating] = useState(wasUpdating)
  if (wasUpdating !== lastUpdating) {
    setLastUpdating(wasUpdating)
    if (lastUpdating && !wasUpdating) void invalidate(queryClient, 'getBacktest')
  }
  const update = useMutation({
    ...updateModelsMutation(),
    onSuccess: (next) => {
      queryClient.setQueryData(getModelHealthOptions().queryKey, next)
      toast.success('Risk model update started', { description: 'It takes about 2 minutes.' })
    },
    onError: (err) => toast.error('Could not start the update', { description: problemMessage(err) }),
  })

  return (
    <div className="flex flex-col gap-4">
      <Tabs value={country} onValueChange={(value) => setCountry(value as Country)}>
        <TabsList>
          {COUNTRIES.map((c) => (
            <TabsTrigger key={c.value} value={c.value}>
              {c.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      {health && (
        <div className="mx-auto w-full max-w-7xl">
          <ModelHealthCard
            health={health}
            canUpdate={me?.role === 'owner'}
            isStarting={update.isPending}
            onUpdate={() => update.mutate({})}
          />
        </div>
      )}
      {error ? <QueryError error={error} /> : <BacktestView result={data} isLoading={isPending} />}
    </div>
  )
}
