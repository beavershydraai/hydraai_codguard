import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import {
  BanIcon,
  FilterIcon,
  InfoIcon,
  PackageXIcon,
  PhoneOffIcon,
  PiggyBankIcon,
  SparklesIcon,
  type LucideIcon,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts'

import type { DashboardSummary } from '@/api/gen'
import { getShopOptions } from '@/api/gen/@tanstack/react-query.gen'
import { Badge } from '@/components/reui/badge'
import { Frame, FramePanel } from '@/components/ui/frame'
import { buttonVariants } from '@/components/ui/button'
import { type ChartConfig, ChartContainer, ChartTooltip, ChartTooltipContent } from '@/components/ui/chart'
import { Item, ItemMedia } from '@/components/ui/item'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { COUNTRY_LABELS, DECISION_ACTION_LABELS, formatMoney, formatPercent } from '@/lib/labels'
import { cn } from '@/lib/utils'
import { useOnboardingStore } from '@/stores/onboarding'

import { type Period, PERIODS } from './data'

// ROI dashboard (E7.5), built with the grammar of ReUI dashboard-1: a header with the period
// switch, KPI cards in a Frame with gradient icon tiles, then chart cards. Predicted figures carry
// the "estimated" label.

type Kpi = {
  title: string
  icon: LucideIcon
  iconBg: string
  value: string
  note: ReactNode
  estimated?: boolean
  help: string
}

export function RoiDashboard({
  summary,
  isLoading,
  period,
  onPeriodChange,
  country,
  onCountryChange,
}: {
  summary: DashboardSummary | undefined
  isLoading: boolean
  period: Period
  onPeriodChange: (period: Period) => void
  country: string
  onCountryChange: (country: string) => void
}) {
  const empty = !isLoading && summary && summary.orders_screened === 0

  return (
    <TooltipProvider delay={150}>
      <div className="@container mx-auto flex w-full max-w-7xl flex-col gap-3">
        {/* Header */}
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              How COD Guard has helped your shop in {COUNTRY_LABELS[country] ?? country} over the last{' '}
              {PERIODS.find((p) => p.value === period)!.label}.
            </p>
          </div>
          <Tabs value={country} onValueChange={onCountryChange}>
            <TabsList>
              {Object.entries(COUNTRY_LABELS).map(([code, label]) => (
                <TabsTrigger key={code} value={code}>
                  {label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <Tabs value={period} onValueChange={(value) => onPeriodChange(value as Period)}>
            <TabsList>
              {PERIODS.map((p) => (
                <TabsTrigger key={p.value} value={p.value}>
                  {p.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>

        <SetupBanner />

        {empty ? (
          <EmptyDashboard />
        ) : (
          <>
            <section aria-label="Key figures">
              <KpiCards summary={summary} isLoading={isLoading} />
            </section>
            <section
              aria-label="Actions and delivery outcomes"
              className="grid min-w-0 items-stretch gap-3 @5xl:grid-cols-2"
            >
              <ActionsChart summary={summary} isLoading={isLoading} />
              <OutcomesCard summary={summary} isLoading={isLoading} />
            </section>
          </>
        )}
      </div>
    </TooltipProvider>
  )
}

function KpiCards({ summary, isLoading }: { summary?: DashboardSummary; isLoading: boolean }) {
  const contacted = summary?.actions
    .filter((a) => a.action !== 'ship_now' && a.action !== 'hold_for_review')
    .reduce((sum, a) => sum + a.count, 0)
  const finished = summary ? summary.delivered + summary.delivery_failed : 0
  const kpis: Kpi[] = summary
    ? [
        {
          title: 'Orders screened',
          icon: FilterIcon,
          iconBg: 'bg-sky-500',
          value: summary.orders_screened.toLocaleString('en-US'),
          note: `${contacted ?? 0} needed buyer contact`,
          help: 'Orders scored for risk in this period.',
        },
        {
          title: 'Cancelled before shipping',
          icon: BanIcon,
          iconBg: 'bg-amber-500',
          value: summary.cancelled_before_ship.toLocaleString('en-US'),
          note: 'No round-trip shipping fees',
          help: 'Orders cancelled (by the buyer, reported as "I didn\'t order this", or by the shop) before they reached the carrier.',
        },
        {
          title: 'Failed deliveries',
          icon: PackageXIcon,
          iconBg: 'bg-rose-500',
          value: summary.delivery_failed.toLocaleString('en-US'),
          note: finished
            ? `${formatPercent(summary.delivery_failed / finished, 1)} of orders with a delivery outcome`
            : 'No delivery outcomes yet',
          help: 'Buyer-caused failures only: refused or unreachable.',
        },
        {
          title: 'Savings',
          icon: PiggyBankIcon,
          iconBg: 'bg-emerald-500',
          value: formatMoney(summary.estimated_savings_vnd, summary.currency),
          note: 'Compared with not using COD Guard',
          estimated: true,
          help: "For each contacted order: the share of failed deliveries its action is expected to prevent times the order's expected loss, minus the contact cost in Settings.",
        },
        {
          title: 'Good orders contacted',
          icon: PhoneOffIcon,
          iconBg: 'bg-violet-500',
          value: formatPercent(summary.good_orders_contacted_rate, 1),
          note: 'Delivered orders that were still contacted',
          estimated: true,
          help: 'Share of good orders that still got a call or a link. Lower means fewer genuine buyers bothered.',
        },
      ]
    : []

  return (
    <Frame className="@container w-full">
      <div className="grid gap-1 @2xl:grid-cols-2 @3xl:grid-cols-3 @6xl:grid-cols-5">
        {isLoading || !summary
          ? Array.from({ length: 5 }, (_, i) => (
              <FramePanel key={i}>
                <Skeleton className="h-10 w-32" />
                <Skeleton className="mt-5 h-7 w-24" />
              </FramePanel>
            ))
          : kpis.map((kpi) => <KpiCard key={kpi.title} kpi={kpi} />)}
      </div>
    </Frame>
  )
}

function KpiCard({ kpi }: { kpi: Kpi }) {
  const Icon = kpi.icon
  return (
    <FramePanel>
      <div className="flex items-center gap-2.5">
        <Item
          className={cn(
            'p-0',
            'flex size-10 items-center justify-center border-2 border-background [background-image:radial-gradient(48.05%_48.05%_at_50%_5.95%,rgba(255,255,255,0.4)_0%,rgba(255,255,255,0)_100%)] shadow-[0_1px_3px_0_rgba(0,0,0,0.14)] dark:border [&_svg]:size-5 [&_svg]:text-white',
            kpi.iconBg,
          )}
        >
          <ItemMedia variant="icon" className="size-auto">
            <Icon aria-hidden="true" />
          </ItemMedia>
        </Item>
        <div className="flex min-w-0 items-center gap-1">
          <h3 className="text-sm leading-tight font-medium">{kpi.title}</h3>
          <Tooltip>
            <TooltipTrigger
              className="inline-flex shrink-0 rounded-full p-0.5 text-muted-foreground/70 hover:text-foreground"
              aria-label={`Explain: ${kpi.title}`}
            >
              <InfoIcon className="size-3.5" aria-hidden="true" />
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-60 text-xs leading-5">
              {kpi.help}
            </TooltipContent>
          </Tooltip>
        </div>
      </div>
      <div className="mt-5 space-y-1.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xl font-medium tracking-tight tabular-nums">{kpi.value}</span>
          {kpi.estimated && (
            <Badge variant="info-light" size="sm">
              estimated
            </Badge>
          )}
        </div>
        <p className="text-sm leading-tight text-muted-foreground">{kpi.note}</p>
      </div>
    </FramePanel>
  )
}

const actionsConfig = { count: { label: 'Orders', color: 'var(--color-sky-500)' } } satisfies ChartConfig

function ActionsChart({ summary, isLoading }: { summary?: DashboardSummary; isLoading: boolean }) {
  const data = (summary?.actions ?? []).map((a) => ({
    action: DECISION_ACTION_LABELS[a.action],
    count: a.count,
  }))
  return (
    <Frame className="@container h-full w-full">
      <FramePanel className="flex h-full flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-medium">Actions by type</h2>
          <span className="text-xs text-muted-foreground">By each order's current decision</span>
        </div>
        {isLoading ? (
          <Skeleton className="h-56 w-full" />
        ) : (
          <ChartContainer config={actionsConfig} className="h-56 w-full">
            <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
              <CartesianGrid horizontal={false} />
              <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={false} />
              <YAxis type="category" dataKey="action" width={120} tickLine={false} axisLine={false} />
              <ChartTooltip cursor={false} content={<ChartTooltipContent hideLabel />} />
              <Bar dataKey="count" fill="var(--color-count)" radius={4} />
            </BarChart>
          </ChartContainer>
        )}
      </FramePanel>
    </Frame>
  )
}

function OutcomesCard({ summary, isLoading }: { summary?: DashboardSummary; isLoading: boolean }) {
  const rows = summary
    ? [
        { label: 'Delivered', value: summary.delivered, tone: 'bg-success' },
        { label: 'Cancelled before shipping', value: summary.cancelled_before_ship, tone: 'bg-warning' },
        { label: 'Delivery failed', value: summary.delivery_failed, tone: 'bg-destructive' },
      ]
    : []
  const total = rows.reduce((sum, r) => sum + r.value, 0)

  return (
    <Frame className="@container h-full w-full">
      <FramePanel className="flex h-full flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-medium">Final order outcomes</h2>
          <Link to="/backtest" className={cn(buttonVariants({ variant: 'link', size: 'sm' }), 'h-auto p-0')}>
            View model backtest
          </Link>
        </div>
        {isLoading || !summary ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <>
            <div
              className="flex h-3 w-full overflow-hidden rounded-full bg-muted"
              role="img"
              aria-label="Delivery outcome shares"
            >
              {rows.map((r) => (
                <div
                  key={r.label}
                  className={r.tone}
                  style={{ width: total ? `${(r.value / total) * 100}%` : 0 }}
                />
              ))}
            </div>
            <ul className="flex flex-col gap-3">
              {rows.map((r) => (
                <li key={r.label} className="flex items-center justify-between gap-3 text-sm">
                  <span className="flex items-center gap-2">
                    <span className={cn('size-2.5 rounded-full', r.tone)} aria-hidden="true" />
                    {r.label}
                  </span>
                  <span className="tabular-nums">
                    {r.value.toLocaleString('en-US')}
                    <span className="ms-2 text-xs text-muted-foreground">
                      {total ? formatPercent(r.value / total) : '—'}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-auto text-xs text-muted-foreground">
              Orders still in progress (awaiting confirmation, awaiting deposit, in transit) are not counted.
            </p>
          </>
        )}
      </FramePanel>
    </Frame>
  )
}

function EmptyDashboard() {
  return (
    <Frame>
      <FramePanel className="flex flex-col items-center gap-4 py-14 text-center">
        <Item variant="outline" className="size-12 justify-center p-0">
          <ItemMedia variant="icon" className="size-auto">
            <FilterIcon className="size-5 text-muted-foreground" aria-hidden="true" />
          </ItemMedia>
        </Item>
        <div className="max-w-sm space-y-1">
          <h2 className="font-medium">No orders in this period yet</h2>
          <p className="text-sm text-muted-foreground">
            Import orders from a file or connect your sales tool. Figures appear as soon as the first order is
            scored.
          </p>
        </div>
        <Link to="/orders" className={buttonVariants()}>
          Go to Orders
        </Link>
      </FramePanel>
    </Frame>
  )
}

/** Points a new shop owner at the setup wizard until they finish or skip it (E7.1). */
function SetupBanner() {
  const { data: shop } = useQuery(getShopOptions())
  const done = useOnboardingStore((s) => (shop ? s.done.includes(shop.id) : true))
  if (!shop || done) return null
  return (
    <Frame>
      <FramePanel className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <SparklesIcon className="size-5 text-primary" aria-hidden="true" />
          <div>
            <p className="text-sm font-medium">Set up your shop in 1 minute</p>
            <p className="text-xs text-muted-foreground">
              Failed delivery cost, contact hours and the default policy.
            </p>
          </div>
        </div>
        <Link to="/onboarding" className={buttonVariants({ size: 'sm' })}>
          Get started
        </Link>
      </FramePanel>
    </Frame>
  )
}
