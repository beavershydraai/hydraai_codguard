import { useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'

import { getBacktestOptions } from '@/api/gen/@tanstack/react-query.gen'
import { BacktestView } from '@/components/blocks/dashboard-1/components/backtest-view'
import { QueryError } from '@/components/query-error'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

export const Route = createFileRoute('/_shop/backtest')({
  staticData: { crumb: 'Backtest' },
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
  const [country, setCountry] = useState<Country>('VN')
  const { data, error, isPending } = useQuery({
    ...getBacktestOptions({ query: { country } }),
    staleTime: 5 * 60_000,
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
      {error ? <QueryError error={error} /> : <BacktestView result={data} isLoading={isPending} />}
    </div>
  )
}
