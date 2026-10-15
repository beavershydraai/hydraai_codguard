import { CartesianGrid, Line, LineChart, XAxis, YAxis } from 'recharts'

import type { BacktestResult } from '@/api/gen'
import { Badge } from '@/components/reui/badge'
import { Frame, FramePanel } from '@/components/ui/frame'
import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDateTime, formatPercent, formatVnd } from '@/lib/labels'
import { cn } from '@/lib/utils'

import { type Policy, POLICY_LABELS } from './data'

// Backtest result (E7.5, E9.1/E9.3) in the chart-card grammar of ReUI dashboard-1.

const liftConfig = {
  cod_guard: { label: POLICY_LABELS.cod_guard, color: 'var(--color-emerald-500)' },
  phone_history_only: { label: POLICY_LABELS.phone_history_only, color: 'var(--color-sky-500)' },
  call_everyone: { label: POLICY_LABELS.call_everyone, color: 'var(--color-amber-500)' },
} satisfies ChartConfig

export function BacktestView({ result, isLoading }: { result?: BacktestResult; isLoading: boolean }) {
  if (isLoading || !result) {
    return (
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-3">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-80 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  // One row per "share contacted", one column per policy.
  const points = result.lift[0]?.points.map((point, i) => ({
    contacted: point.contacted_share,
    ...Object.fromEntries(
      result.lift.map((series) => [series.policy, series.points[i]?.failures_caught_share ?? null]),
    ),
  }))
  const best = [...result.comparison].sort((a, b) => b.monthly_savings_vnd - a.monthly_savings_vnd)

  return (
    <div className="@container mx-auto flex w-full max-w-7xl flex-col gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Model backtest</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {result.dataset} · {result.orders.toLocaleString('en-US')} orders · assumes {result.orders_per_day}{' '}
          orders/day, {formatVnd(result.failed_delivery_cost_vnd)} per failed delivery · run at{' '}
          {formatDateTime(result.generated_at)}
        </p>
      </div>

      <div className="grid min-w-0 items-stretch gap-3 @5xl:grid-cols-[3fr_2fr]">
        <Frame className="@container h-full w-full">
          <FramePanel className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-medium">Failed deliveries caught vs. orders contacted</h2>
              <Badge variant="info-light" size="sm">
                estimated
              </Badge>
            </div>
            <ChartContainer config={liftConfig} className="aspect-auto h-72 w-full">
              <LineChart data={points} margin={{ left: 4, right: 12, top: 8 }}>
                <CartesianGrid vertical={false} />
                <XAxis
                  dataKey="contacted"
                  type="number"
                  domain={[0, 1]}
                  tickFormatter={(v: number) => formatPercent(v)}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  domain={[0, 1]}
                  tickFormatter={(v: number) => formatPercent(v)}
                  tickLine={false}
                  axisLine={false}
                  width={44}
                />
                <ChartTooltip
                  content={
                    <ChartTooltipContent
                      labelFormatter={(_, payload) =>
                        `${formatPercent(Number(payload?.[0]?.payload?.contacted ?? 0))} of orders contacted`
                      }
                      formatter={(value, name) => (
                        <span className="flex w-full justify-between gap-3">
                          <span className="text-muted-foreground">{POLICY_LABELS[name as Policy]}</span>
                          <span className="tabular-nums">{formatPercent(Number(value))}</span>
                        </span>
                      )}
                    />
                  }
                />
                <ChartLegend content={<ChartLegendContent />} />
                {result.lift.map((series) => (
                  <Line
                    key={series.policy}
                    dataKey={series.policy}
                    type="monotone"
                    stroke={`var(--color-${series.policy})`}
                    strokeWidth={series.policy === 'cod_guard' ? 2.5 : 1.5}
                    strokeDasharray={series.policy === 'call_everyone' ? '4 4' : undefined}
                    dot={false}
                  />
                ))}
              </LineChart>
            </ChartContainer>
            <p className="text-xs text-muted-foreground">
              Higher on the left is better: more failed deliveries caught while contacting fewer orders.
            </p>
          </FramePanel>
        </Frame>

        <Frame className="@container h-full w-full">
          <FramePanel className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-medium">5 policies compared</h2>
              <Badge variant="info-light" size="sm">
                estimated
              </Badge>
            </div>
            <ul className="flex flex-col divide-y">
              {best.map((row) => (
                <li key={row.policy} className="flex flex-col gap-1.5 py-3 first:pt-0 last:pb-0">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className={cn('text-sm', row.policy === 'cod_guard' && 'font-semibold')}>
                      {POLICY_LABELS[row.policy]}
                    </span>
                    <span
                      className={cn(
                        'text-sm tabular-nums',
                        row.policy === 'cod_guard' && 'font-semibold text-success',
                      )}
                    >
                      {formatVnd(row.monthly_savings_vnd)}/month
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground tabular-nums">
                    <span>Contacts {formatPercent(row.contact_rate)} of orders</span>
                    <span>Catches {formatPercent(row.failures_caught_rate)} of failed deliveries</span>
                  </div>
                </li>
              ))}
            </ul>
          </FramePanel>
        </Frame>
      </div>
    </div>
  )
}
