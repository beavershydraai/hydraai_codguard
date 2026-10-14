import { Link } from '@tanstack/react-router'
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  GiftIcon,
  MessageSquareTextIcon,
  PencilIcon,
  PhoneCallIcon,
  ScaleIcon,
  ShieldAlertIcon,
} from 'lucide-react'
import type { ReactNode } from 'react'

import type { Call, ContactAttempt, OrderDetail, OrderEvent, RiskScore, Signal } from '@/api/gen'
import { OrderStatusBadge } from '@/components/order-status-badge'
import { Badge } from '@/components/reui/badge'
import {
  Timeline,
  TimelineContent,
  TimelineIndicator,
  TimelineItem,
  TimelineSeparator,
} from '@/components/reui/timeline'
import { Frame, FrameHeader, FramePanel, FrameTitle } from '@/components/reui/frame'
import { TierBadge } from '@/components/tier-badge'
import { Button } from '@/components/ui/button'
import { Item, ItemMedia } from '@/components/ui/item'
import { Separator } from '@/components/ui/separator'
import {
  BLOCK_REASON_LABELS,
  CALL_OUTCOME_LABELS,
  CALL_STATUS_LABELS,
  CONTACT_CHANNEL_LABELS,
  DECISION_ACTION_LABELS,
  formatDateTime,
  formatPercent,
  formatRelative,
  formatVnd,
  HARD_RULE_LABELS,
  SALES_CHANNEL_LABELS,
  SIGNAL_GROUP_LABELS,
} from '@/lib/labels'
import { cn } from '@/lib/utils'

// Order page (E7.3), laid out like ReUI receipt-2: a header strip with the order actions, a hero
// frame with status and the amount still to collect, then the order journey timeline beside the
// risk, decision, contact and order details.

const TL_INDICATOR_BASE =
  'size-2.5 border-0 group-data-[orientation=vertical]/timeline:-left-3 group-data-[orientation=vertical]/timeline:-translate-x-1/2 group-data-[orientation=vertical]/timeline:top-1.25'
const TL_SEPARATOR =
  'bg-foreground group-data-[orientation=vertical]/timeline:-left-3 group-data-[orientation=vertical]/timeline:-translate-x-1/2 group-data-[orientation=vertical]/timeline:h-[calc(100%-1.5rem)] group-data-[orientation=vertical]/timeline:translate-y-5.5'
const TL_ITEM_CLASS =
  'group-data-[orientation=vertical]/timeline:ms-5 group-data-[orientation=vertical]/timeline:not-last:pb-5'

const EVENT_TONE: Partial<Record<OrderEvent['type'], string>> = {
  override: 'bg-warning',
  delivery_result: 'bg-success',
  call_completed: 'bg-info',
  buyer_responded: 'bg-info',
}

export type OrderDetailActions = {
  onCall?: () => void
  onEdit?: () => void
  onOverride?: () => void
  /** Shown for an open confirmation link: preview of the simulated Zalo ZNS / SMS. */
  onPreviewMessage?: (contact: ContactAttempt) => void
  callDisabledReason?: string | null
}

export function OrderDetailView({ order, actions }: { order: OrderDetail; actions: OrderDetailActions }) {
  const code = order.external_id ?? order.id
  const editable = (order.allowed_overrides?.length ?? 0) > 0

  return (
    <section aria-labelledby="order-heading" className="mx-auto w-full max-w-6xl">
      {/* Page header */}
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <Button variant="ghost" size="sm" asChild className="-ms-2 text-muted-foreground">
          <Link to="/orders">
            <ArrowLeftIcon aria-hidden="true" />
            Đơn hàng
          </Link>
        </Button>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            onClick={actions.onCall}
            disabled={!actions.onCall || !!actions.callDisabledReason}
            title={actions.callDisabledReason ?? undefined}
          >
            <PhoneCallIcon aria-hidden="true" />
            AI gọi xác nhận
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={actions.onEdit} disabled={!editable}>
            <PencilIcon aria-hidden="true" />
            Sửa đơn
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={actions.onOverride} disabled={!editable}>
            <ScaleIcon aria-hidden="true" />
            Quyết định thay
          </Button>
        </div>
      </header>

      {/* Hero strip: status + order id + amount to collect */}
      <Frame className="mb-6">
        <FramePanel>
          <div className="grid grid-cols-1 gap-5 md:grid-cols-[minmax(0,1fr)_auto_auto] md:items-center md:gap-8">
            <div className="flex min-w-0 flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <OrderStatusBadge status={order.status} />
                {order.tier && <TierBadge tier={order.tier} />}
                {order.is_gift && (
                  <Badge variant="info-light">
                    <GiftIcon aria-hidden="true" className="size-3" />
                    Đơn quà tặng
                  </Badge>
                )}
                <span className="text-xs text-muted-foreground">
                  Đặt {formatRelative(order.placed_at)} · {SALES_CHANNEL_LABELS[order.channel]}
                </span>
              </div>
              <FrameTitle id="order-heading" className="text-xl tracking-tight md:text-2xl">
                Đơn {code}
              </FrameTitle>
              <p className="text-sm leading-snug text-muted-foreground">
                {order.buyer_name} · <span className="tabular-nums">{order.buyer_phone}</span>
              </p>
            </div>

            <Separator orientation="vertical" className="hidden h-14 md:block data-vertical:self-center" />

            <div className="flex flex-col gap-1 md:items-end">
              <span className="text-xs font-medium tracking-[0.16em] text-muted-foreground uppercase">
                Còn phải thu
              </span>
              <span className="text-2xl leading-none font-semibold tracking-tight tabular-nums md:text-3xl">
                {formatVnd(order.cod_amount_vnd)}
              </span>
              <span className="text-xs text-muted-foreground tabular-nums">
                Tổng {formatVnd(order.total_vnd)}
                {order.prepaid_vnd > 0 && ` · Trả trước ${formatVnd(order.prepaid_vnd)}`}
              </span>
            </div>
          </div>
        </FramePanel>
      </Frame>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)] lg:gap-8">
        <JourneyPanel order={order} />

        <div className="flex min-w-0 flex-col gap-6">
          <RiskPanel score={order.current_score ?? null} />
          <DecisionPanel order={order} />
          <ContactsPanel order={order} onPreviewMessage={actions.onPreviewMessage} />
          <DetailsPanel order={order} />
          <PartiesPanel order={order} />
          <ScoreHistoryPanel runs={order.score_history ?? []} />
        </div>
      </div>
    </section>
  )
}

// ── Journey ──

function JourneyPanel({ order }: { order: OrderDetail }) {
  const events = [...(order.timeline ?? [])].sort((a, b) => a.at.localeCompare(b.at))
  const next = order.decision?.next_action

  return (
    <Frame className="self-start lg:sticky lg:top-6">
      <FrameHeader>
        <FrameTitle className="text-base">Hành trình đơn</FrameTitle>
      </FrameHeader>
      <FramePanel className="flex flex-col gap-5">
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground">Chưa có sự kiện nào.</p>
        ) : (
          <Timeline defaultValue={events.length} className="gap-0">
            {events.map((event, index) => {
              const isLast = index === events.length - 1
              return (
                <TimelineItem key={`${event.at}-${index}`} step={index + 1} className={TL_ITEM_CLASS}>
                  {!isLast && <TimelineSeparator className={TL_SEPARATOR} />}
                  <TimelineIndicator
                    className={cn(
                      TL_INDICATOR_BASE,
                      EVENT_TONE[event.type] ?? 'bg-foreground',
                      isLast && 'ring-2 ring-foreground/20',
                    )}
                  />
                  <TimelineContent className="ps-3 text-foreground">
                    <div className="flex flex-col gap-0.5">
                      <span className="text-sm leading-snug font-medium">{event.message_vi}</span>
                      {event.reason && (
                        <span className="text-xs leading-snug text-muted-foreground">
                          Lý do: {event.reason}
                        </span>
                      )}
                      <time className="text-xs text-muted-foreground tabular-nums" dateTime={event.at}>
                        {formatDateTime(event.at)} · {actorLabel(event.actor)}
                      </time>
                    </div>
                  </TimelineContent>
                </TimelineItem>
              )
            })}
          </Timeline>
        )}

        {next && (
          <div className="flex flex-col gap-2 border-t pt-4">
            <span className="text-xs font-medium tracking-[0.16em] text-muted-foreground uppercase">
              Bước tiếp theo
            </span>
            <p className="flex items-center gap-1.5 text-sm">
              <ArrowRightIcon className="size-3.5 text-muted-foreground" aria-hidden="true" />
              {DECISION_ACTION_LABELS[next]}
              {order.decision?.next_action_at && (
                <span className="text-muted-foreground">
                  {' '}
                  nếu chưa phản hồi trước {formatDateTime(order.decision.next_action_at)}
                </span>
              )}
            </p>
          </div>
        )}
      </FramePanel>
    </Frame>
  )
}

function actorLabel(actor: string): string {
  const known: Record<string, string> = {
    system: 'Hệ thống',
    engine: 'Decision engine',
    ai_call: 'AI gọi',
    buyer: 'Người mua',
    carrier: 'Đơn vị vận chuyển',
  }
  return known[actor] ?? actor
}

// ── Risk ──

function RiskPanel({ score }: { score: RiskScore | null }) {
  if (!score) {
    return (
      <PanelFrame eyebrow="Rủi ro bom hàng" title="Chưa chấm điểm">
        <p className="text-sm text-muted-foreground">Đơn mới vào, hệ thống đang chấm điểm.</p>
      </PanelFrame>
    )
  }
  if (score.status === 'skipped') {
    return (
      <PanelFrame eyebrow="Rủi ro bom hàng" title="Bỏ qua chấm điểm">
        <p className="text-sm text-muted-foreground">
          {score.skipped_reason ? HARD_RULE_LABELS[score.skipped_reason] : 'Đơn không cần chấm điểm'}: không
          liên hệ người mua.
        </p>
      </PanelFrame>
    )
  }

  const signals = score.top_signals ?? []
  const maxContribution = Math.max(0.01, ...signals.map((s) => Math.abs(s.contribution)))

  return (
    <PanelFrame
      eyebrow="Rủi ro bom hàng"
      title={
        <span className="flex flex-wrap items-center gap-2">
          <span className="tabular-nums">{score.risk_score}/100</span>
          {score.tier && <TierBadge tier={score.tier} />}
        </span>
      }
    >
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Metric
          label="Xác suất bom hàng"
          value={score.probability != null ? formatPercent(score.probability, 1) : '—'}
          estimated
        />
        <Metric
          label="Thiệt hại dự kiến"
          value={score.expected_loss_vnd != null ? formatVnd(score.expected_loss_vnd) : '—'}
          estimated
        />
        <Metric label="Chi phí 1 lần giao hỏng" value={formatVnd(score.failed_delivery_cost_vnd)} />
      </dl>

      {(score.hard_rules?.length ?? 0) > 0 && (
        <div className="flex flex-wrap gap-2">
          {score.hard_rules!.map((rule) => (
            <Badge key={rule} variant="destructive-outline">
              <ShieldAlertIcon aria-hidden="true" className="size-3" />
              {HARD_RULE_LABELS[rule]}
            </Badge>
          ))}
        </div>
      )}

      {(score.reasons?.length ?? 0) > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-medium">Lý do</h3>
          <ol className="flex flex-col gap-1.5">
            {score.reasons!.map((reason, i) => (
              <li key={reason.text_vi} className="flex gap-2 text-sm">
                <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium tabular-nums">
                  {i + 1}
                </span>
                {reason.text_vi}
              </li>
            ))}
          </ol>
        </div>
      )}

      {signals.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-medium">Tín hiệu đóng góp nhiều nhất</h3>
          <ul className="flex flex-col gap-2.5">
            {signals.map((signal) => (
              <SignalRow key={signal.key} signal={signal} max={maxContribution} />
            ))}
          </ul>
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        Mô hình {score.model_version ?? '—'} · chấm lúc {formatDateTime(score.scored_at)}. Điểm và hành động
        do mô hình và decision engine quyết định; Gemini chỉ viết lý do.
      </p>
    </PanelFrame>
  )
}

function SignalRow({ signal, max }: { signal: Signal; max: number }) {
  const raises = signal.contribution > 0
  const width = `${Math.round((Math.abs(signal.contribution) / max) * 100)}%`
  return (
    <li className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="min-w-0">
          {signal.label_vi}
          <span className="ms-1.5 text-xs text-muted-foreground">{SIGNAL_GROUP_LABELS[signal.group]}</span>
        </span>
        <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
          {formatSignalValue(signal.value)}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted" aria-hidden="true">
        <div
          className={cn('h-full rounded-full', raises ? 'bg-destructive' : 'bg-success')}
          style={{ width }}
        />
      </div>
      <span className="sr-only">{raises ? 'Làm tăng rủi ro' : 'Làm giảm rủi ro'}</span>
    </li>
  )
}

function formatSignalValue(value: Signal['value']): string {
  if (typeof value === 'boolean') return value ? 'Có' : 'Không'
  if (typeof value === 'number' && value >= 10_000) return formatVnd(value)
  return String(value)
}

// ── Decision ──

function DecisionPanel({ order }: { order: OrderDetail }) {
  const decision = order.decision
  if (!decision) {
    return (
      <PanelFrame eyebrow="Quyết định" title="Chưa có quyết định">
        <p className="text-sm text-muted-foreground">Quyết định được đưa ra ngay sau khi chấm điểm.</p>
      </PanelFrame>
    )
  }
  return (
    <PanelFrame
      eyebrow="Quyết định"
      title={
        <span className="flex flex-wrap items-center gap-2">
          {DECISION_ACTION_LABELS[decision.action]}
          <Badge variant={decision.decided_by === 'staff' ? 'warning-outline' : 'outline'}>
            {decision.decided_by === 'staff' ? 'Nhân viên quyết định' : 'Decision engine'}
          </Badge>
        </span>
      }
    >
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Metric label="Thời điểm" value={formatDateTime(decision.decided_at)} />
        <Metric label="Policy" value={`Phiên bản ${decision.policy_version}`} />
        <Metric
          label="Thiệt hại dự kiến / chi phí liên hệ"
          value={`${decision.expected_loss_vnd != null ? formatVnd(decision.expected_loss_vnd) : '—'} / ${
            decision.contact_cost_vnd != null ? formatVnd(decision.contact_cost_vnd) : '—'
          }`}
          estimated
        />
      </dl>
      {(decision.block_reasons?.length ?? 0) > 0 && (
        <div className="flex flex-col gap-1.5">
          <h3 className="text-sm font-medium">Không liên hệ vì</h3>
          <div className="flex flex-wrap gap-2">
            {decision.block_reasons!.map((reason) => (
              <Badge key={reason} variant="secondary">
                {BLOCK_REASON_LABELS[reason]}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </PanelFrame>
  )
}

// ── Contacts and calls ──

function ContactsPanel({
  order,
  onPreviewMessage,
}: {
  order: OrderDetail
  onPreviewMessage?: (contact: ContactAttempt) => void
}) {
  const contacts = [...(order.contacts ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at))
  const calls = new Map((order.calls ?? []).map((call) => [call.id, call]))

  return (
    <PanelFrame eyebrow="Lịch sử liên hệ" title={`${contacts.length} lần liên hệ`}>
      {contacts.length === 0 ? (
        <p className="text-sm text-muted-foreground">Chưa liên hệ người mua.</p>
      ) : (
        <ul className="flex flex-col divide-y">
          {contacts.map((contact) => {
            const call = contact.call_id ? calls.get(contact.call_id) : undefined
            return (
              <li key={contact.id} className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Item variant="outline" className="size-8 w-auto shrink-0 justify-center px-1.5 py-1">
                      <ItemMedia variant="icon" className="size-auto">
                        {contact.channel === 'ai_call' ? (
                          <PhoneCallIcon className="size-4 text-muted-foreground" aria-hidden="true" />
                        ) : (
                          <MessageSquareTextIcon
                            className="size-4 text-muted-foreground"
                            aria-hidden="true"
                          />
                        )}
                      </ItemMedia>
                    </Item>
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">
                        {CONTACT_CHANNEL_LABELS[contact.channel]}
                        {call && ` · lần ${call.attempt}`}
                      </span>
                      <span className="text-xs text-muted-foreground tabular-nums">
                        {formatDateTime(contact.created_at)}
                      </span>
                    </div>
                  </div>
                  <ContactResult contact={contact} call={call} />
                </div>
                {call?.summary_vi && <CallSummary call={call} />}
                {contact.channel !== 'ai_call' && onPreviewMessage && (
                  <div className="flex flex-wrap items-center gap-2">
                    {contact.link_expires_at && (
                      <span className="text-xs text-muted-foreground">
                        Link hết hạn {formatDateTime(contact.link_expires_at)}
                      </span>
                    )}
                    <Button
                      variant="link"
                      size="sm"
                      className="h-auto p-0"
                      onClick={() => onPreviewMessage(contact)}
                    >
                      Xem tin nhắn đã gửi
                    </Button>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </PanelFrame>
  )
}

function ContactResult({ contact, call }: { contact: ContactAttempt; call?: Call }) {
  if (call) {
    if (call.outcome) {
      const tone = ['confirmed', 'edited'].includes(call.outcome)
        ? 'success-outline'
        : ['cancelled', 'not_ordered'].includes(call.outcome)
          ? 'destructive-outline'
          : 'warning-outline'
      return <Badge variant={tone}>{CALL_OUTCOME_LABELS[call.outcome]}</Badge>
    }
    return <Badge variant="info-outline">{CALL_STATUS_LABELS[call.status]}</Badge>
  }
  if (contact.responded_at) return <Badge variant="success-outline">Đã phản hồi</Badge>
  return <Badge variant="outline">Chưa phản hồi</Badge>
}

function CallSummary({ call }: { call: Call }) {
  return (
    <div className="flex flex-col gap-1 rounded-md bg-muted/50 p-3 text-sm">
      <p>{call.summary_vi}</p>
      {(call.changes?.length ?? 0) > 0 && (
        <ul className="text-xs text-muted-foreground">
          {call.changes!.map((change) => (
            <li key={`${change.field}-${change.new_value}`}>Thay đổi: {change.new_value}</li>
          ))}
        </ul>
      )}
      {call.buyer_requests && <p className="text-xs text-muted-foreground">Yêu cầu: {call.buyer_requests}</p>}
      {call.duration_seconds != null && (
        <p className="text-xs text-muted-foreground tabular-nums">
          {call.phone_masked} · {Math.floor(call.duration_seconds / 60)}:
          {String(call.duration_seconds % 60).padStart(2, '0')}
        </p>
      )}
    </div>
  )
}

// ── Items and parties ──

function DetailsPanel({ order }: { order: OrderDetail }) {
  const subtotal = order.items.reduce((sum, item) => sum + item.quantity * item.unit_price_vnd, 0)
  return (
    <Frame>
      <FrameHeader className="gap-1">
        <span className="text-xs font-medium tracking-[0.16em] text-muted-foreground uppercase">
          Sản phẩm
        </span>
        <FrameTitle className="text-base">{order.items.length} sản phẩm</FrameTitle>
      </FrameHeader>
      <FramePanel className="flex flex-col gap-6">
        <div role="list" aria-label="Sản phẩm trong đơn" className="flex flex-col gap-3">
          {order.items.map((item, i) => (
            <article key={`${item.name}-${i}`} role="listitem" className="flex min-w-0 items-start gap-3">
              <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                <h3 className="min-w-0 truncate text-sm leading-snug font-medium">{item.name}</h3>
                <p className="text-xs text-muted-foreground">
                  {[item.variant, `SL ${item.quantity}`, item.sku].filter(Boolean).join(' · ')}
                </p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-0.5 text-sm tabular-nums">
                <span className="font-semibold">{formatVnd(item.quantity * item.unit_price_vnd)}</span>
                {item.quantity > 1 && (
                  <span className="text-xs text-muted-foreground">
                    {formatVnd(item.unit_price_vnd)} / cái
                  </span>
                )}
              </div>
            </article>
          ))}
        </div>

        <Separator />

        <dl className="flex flex-col gap-1.5 self-end sm:min-w-72">
          <SummaryRow label="Tạm tính" value={formatVnd(subtotal)} />
          <SummaryRow label="Phí ship" value={formatVnd(order.shipping_fee_vnd)} />
          {order.discount_vnd > 0 && (
            <SummaryRow label="Giảm giá" value={`-${formatVnd(order.discount_vnd)}`} tone="success" />
          )}
          <SummaryRow label="Tổng" value={formatVnd(order.total_vnd)} />
          {order.prepaid_vnd > 0 && (
            <SummaryRow label="Đã trả trước" value={`-${formatVnd(order.prepaid_vnd)}`} tone="success" />
          )}
          <Separator className="my-1" />
          <SummaryRow label="Thu hộ (COD)" value={formatVnd(order.cod_amount_vnd)} strong />
        </dl>
      </FramePanel>
    </Frame>
  )
}

function PartiesPanel({ order }: { order: OrderDetail }) {
  return (
    <Frame>
      <FramePanel className="grid grid-cols-1 gap-5 sm:grid-cols-3">
        <PartyBlock label="Người mua">
          <p className="font-medium">{order.buyer_name}</p>
          <p className="text-muted-foreground tabular-nums">{order.buyer_phone}</p>
        </PartyBlock>
        <PartyBlock label={order.is_gift ? 'Người nhận (quà tặng)' : 'Người nhận'}>
          <p className="font-medium">{order.recipient_name ?? order.buyer_name}</p>
          {order.is_gift && (
            <p className="text-xs text-muted-foreground">
              Chỉ xác minh với người mua, không liên hệ người nhận.
            </p>
          )}
        </PartyBlock>
        <PartyBlock label="Giao tới">
          <p className="text-muted-foreground">{order.address.raw}</p>
          {order.note && <p className="text-xs text-muted-foreground">Ghi chú: {order.note}</p>}
        </PartyBlock>
      </FramePanel>
    </Frame>
  )
}

function PartyBlock({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <p className="text-xs font-medium tracking-[0.16em] text-muted-foreground uppercase">{label}</p>
      <address className="text-sm leading-snug not-italic">{children}</address>
    </div>
  )
}

function ScoreHistoryPanel({ runs }: { runs: RiskScore[] }) {
  if (runs.length === 0) return null
  return (
    <PanelFrame eyebrow="Lịch sử điểm" title={`${runs.length} lần chấm`}>
      <ul className="flex flex-col divide-y text-sm">
        {runs.map((run) => (
          <li key={run.id} className="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0">
            <span className="text-muted-foreground tabular-nums">{formatDateTime(run.scored_at)}</span>
            <span className="flex items-center gap-2">
              {run.status === 'skipped' ? (
                <span className="text-muted-foreground">Bỏ qua</span>
              ) : (
                <>
                  <span className="tabular-nums">{run.risk_score}/100</span>
                  {run.tier && <TierBadge tier={run.tier} />}
                </>
              )}
            </span>
          </li>
        ))}
      </ul>
    </PanelFrame>
  )
}

// ── Shared ──

function PanelFrame({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string
  title: ReactNode
  children: ReactNode
}) {
  return (
    <Frame>
      <FrameHeader className="gap-1">
        <span className="text-xs font-medium tracking-[0.16em] text-muted-foreground uppercase">
          {eyebrow}
        </span>
        <FrameTitle className="text-base">{title}</FrameTitle>
      </FrameHeader>
      <FramePanel className="flex flex-col gap-5">{children}</FramePanel>
    </Frame>
  )
}

function Metric({ label, value, estimated = false }: { label: string; value: string; estimated?: boolean }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <dt className="text-xs text-muted-foreground">
        {label}
        {estimated && <span className="ms-1 text-[10px] tracking-wide uppercase">(ước tính)</span>}
      </dt>
      <dd className="text-sm font-medium tabular-nums">{value}</dd>
    </div>
  )
}

function SummaryRow({
  label,
  value,
  tone = 'default',
  strong = false,
}: {
  label: string
  value: string
  tone?: 'default' | 'success'
  strong?: boolean
}) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className={cn(strong ? 'text-base font-semibold' : 'text-sm text-muted-foreground')}>{label}</dt>
      <dd
        className={cn(
          'tabular-nums',
          strong ? 'text-base font-semibold' : 'text-sm font-medium',
          tone === 'success' && 'text-success',
        )}
      >
        {value}
      </dd>
    </div>
  )
}
