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
import { Frame, FramePanel } from '@/components/reui/frame'
import { Button } from '@/components/ui/button'
import { type ChartConfig, ChartContainer, ChartTooltip, ChartTooltipContent } from '@/components/ui/chart'
import { Item, ItemMedia } from '@/components/ui/item'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { DECISION_ACTION_LABELS, formatPercent, formatVnd } from '@/lib/labels'
import { cn } from '@/lib/utils'
import { useOnboardingStore } from '@/stores/onboarding'

import { type Period, PERIODS } from './data'

// ROI dashboard (E7.5), built with the grammar of ReUI dashboard-1: a header with the period
// switch, KPI cards in a Frame with gradient icon tiles, then chart cards. Predicted figures carry
// the "ước tính" label.

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
}: {
  summary: DashboardSummary | undefined
  isLoading: boolean
  period: Period
  onPeriodChange: (period: Period) => void
}) {
  const empty = !isLoading && summary && summary.orders_screened === 0

  return (
    <TooltipProvider delayDuration={150}>
      <div className="@container mx-auto flex w-full max-w-7xl flex-col gap-3">
        {/* Header */}
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Tổng quan</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              COD Guard đã giúp shop thế nào trong {PERIODS.find((p) => p.value === period)!.label} qua.
            </p>
          </div>
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
            <section aria-label="Chỉ số chính">
              <KpiCards summary={summary} isLoading={isLoading} />
            </section>
            <section
              aria-label="Hành động và kết quả giao"
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
          title: 'Đơn đã sàng lọc',
          icon: FilterIcon,
          iconBg: 'bg-sky-500',
          value: summary.orders_screened.toLocaleString('vi-VN'),
          note: `${contacted ?? 0} đơn cần liên hệ người mua`,
          help: 'Số đơn được chấm điểm rủi ro trong kỳ.',
        },
        {
          title: 'Hủy trước khi gửi',
          icon: BanIcon,
          iconBg: 'bg-amber-500',
          value: summary.cancelled_before_ship.toLocaleString('vi-VN'),
          note: 'Không tốn phí ship hai chiều',
          help: 'Đơn bị hủy (người mua hủy, báo "không đặt", hoặc shop hủy) trước khi giao cho đơn vị vận chuyển.',
        },
        {
          title: 'Giao thất bại',
          icon: PackageXIcon,
          iconBg: 'bg-rose-500',
          value: summary.delivery_failed.toLocaleString('vi-VN'),
          note: finished
            ? `${formatPercent(summary.delivery_failed / finished, 1)} số đơn đã có kết quả giao`
            : 'Chưa có kết quả giao',
          help: 'Chỉ tính lỗi do người mua: từ chối nhận, không liên lạc được.',
        },
        {
          title: 'Tiền tiết kiệm',
          icon: PiggyBankIcon,
          iconBg: 'bg-emerald-500',
          value: formatVnd(summary.estimated_savings_vnd),
          note: 'So với không dùng COD Guard',
          estimated: true,
          help: 'Phí giao hỏng tránh được trừ chi phí liên hệ, theo chi phí giao thất bại trong Cài đặt.',
        },
        {
          title: 'Đơn tốt bị làm phiền',
          icon: PhoneOffIcon,
          iconBg: 'bg-violet-500',
          value: formatPercent(summary.good_orders_contacted_rate, 1),
          note: 'Đơn giao thành công nhưng vẫn bị liên hệ',
          estimated: true,
          help: 'Tỷ lệ đơn tốt mà shop vẫn gọi hoặc gửi link. Càng thấp càng ít làm phiền khách thật.',
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
            <TooltipTrigger asChild>
              <button
                type="button"
                className="inline-flex shrink-0 rounded-full p-0.5 text-muted-foreground/70 hover:text-foreground"
                aria-label={`Giải thích: ${kpi.title}`}
              >
                <InfoIcon className="size-3.5" aria-hidden="true" />
              </button>
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
              ước tính
            </Badge>
          )}
        </div>
        <p className="text-sm leading-tight text-muted-foreground">{kpi.note}</p>
      </div>
    </FramePanel>
  )
}

const actionsConfig = { count: { label: 'Số đơn', color: 'var(--color-sky-500)' } } satisfies ChartConfig

function ActionsChart({ summary, isLoading }: { summary?: DashboardSummary; isLoading: boolean }) {
  const data = (summary?.actions ?? []).map((a) => ({
    action: DECISION_ACTION_LABELS[a.action],
    count: a.count,
  }))
  return (
    <Frame className="@container h-full w-full">
      <FramePanel className="flex h-full flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-medium">Hành động theo loại</h2>
          <span className="text-xs text-muted-foreground">Theo quyết định hiện tại của mỗi đơn</span>
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
        { label: 'Giao thành công', value: summary.delivered, tone: 'bg-success' },
        { label: 'Hủy trước khi gửi', value: summary.cancelled_before_ship, tone: 'bg-warning' },
        { label: 'Giao thất bại', value: summary.delivery_failed, tone: 'bg-destructive' },
      ]
    : []
  const total = rows.reduce((sum, r) => sum + r.value, 0)

  return (
    <Frame className="@container h-full w-full">
      <FramePanel className="flex h-full flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-medium">Kết quả cuối của đơn</h2>
          <Button variant="link" size="sm" className="h-auto p-0" asChild>
            <Link to="/backtest">Xem backtest mô hình</Link>
          </Button>
        </div>
        {isLoading || !summary ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <>
            <div
              className="flex h-3 w-full overflow-hidden rounded-full bg-muted"
              role="img"
              aria-label="Tỷ lệ kết quả giao"
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
                    {r.value.toLocaleString('vi-VN')}
                    <span className="ms-2 text-xs text-muted-foreground">
                      {total ? formatPercent(r.value / total) : '—'}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-auto text-xs text-muted-foreground">
              Đơn còn đang xử lý (chờ xác nhận, chờ cọc, đang giao) chưa được tính.
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
          <h2 className="font-medium">Chưa có đơn nào trong kỳ này</h2>
          <p className="text-sm text-muted-foreground">
            Nhập đơn từ file hoặc kết nối công cụ bán hàng. Số liệu sẽ hiện ngay khi đơn đầu tiên được chấm
            điểm.
          </p>
        </div>
        <Button asChild>
          <Link to="/orders">Đi tới Đơn hàng</Link>
        </Button>
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
            <p className="text-sm font-medium">Thiết lập shop trong 1 phút</p>
            <p className="text-xs text-muted-foreground">
              Chi phí giao thất bại, giờ liên hệ và policy mặc định.
            </p>
          </div>
        </div>
        <Button size="sm" asChild>
          <Link to="/onboarding">Bắt đầu</Link>
        </Button>
      </FramePanel>
    </Frame>
  )
}
