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
import { Frame, FrameHeader, FramePanel, FrameTitle } from '@/components/ui/frame'
import { TierBadge } from '@/components/tier-badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Item, ItemMedia } from '@/components/ui/item'
import { Separator } from '@/components/ui/separator'
import { Spinner } from '@/components/ui/spinner'
import {
  BLOCK_REASON_LABELS,
  CALL_OUTCOME_LABELS,
  CALL_STATUS_LABELS,
  CONTACT_CHANNEL_LABELS,
  DECISION_ACTION_LABELS,
  formatDateTime,
  formatPercent,
  formatRelative,
  formatMoney,
  HARD_RULE_LABELS,
  REVIEW_REASON_LABELS,
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
  /** Accepts the contact the engine suggested (automation off). */
  onAcceptSuggestion?: () => void
  acceptingSuggestion?: boolean
}

export function OrderDetailView({ order, actions }: { order: OrderDetail; actions: OrderDetailActions }) {
  const code = order.external_id ?? order.id
  const editable = (order.allowed_overrides?.length ?? 0) > 0

  return (
    <section aria-labelledby="order-heading" className="mx-auto w-full max-w-6xl">
      {/* Page header */}
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <Link
          to="/orders"
          className={cn(buttonVariants({ variant: 'ghost', size: 'sm' }), '-ms-2 text-muted-foreground')}
        >
          <ArrowLeftIcon aria-hidden="true" />
          Orders
        </Link>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            onClick={actions.onCall}
            disabled={!actions.onCall || !!actions.callDisabledReason}
            title={actions.callDisabledReason ?? undefined}
          >
            <PhoneCallIcon aria-hidden="true" />
            AI confirmation call
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={actions.onEdit} disabled={!editable}>
            <PencilIcon aria-hidden="true" />
            Edit order
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={actions.onOverride} disabled={!editable}>
            <ScaleIcon aria-hidden="true" />
            Override
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
                    Gift order
                  </Badge>
                )}
                <span className="text-xs text-muted-foreground">
                  Placed {formatRelative(order.placed_at)} · {SALES_CHANNEL_LABELS[order.channel]}
                </span>
              </div>
              <FrameTitle id="order-heading" className="text-xl tracking-tight md:text-2xl">
                Order {code}
              </FrameTitle>
              <p className="text-sm leading-snug text-muted-foreground">
                {order.buyer_name} · <span className="tabular-nums">{order.buyer_phone}</span>
              </p>
            </div>

            <Separator orientation="vertical" className="hidden h-14 md:block data-vertical:self-center" />

            <div className="flex flex-col gap-1 md:items-end">
              <span className="text-xs font-medium tracking-[0.16em] text-muted-foreground uppercase">
                Left to collect
              </span>
              <span className="text-2xl leading-none font-semibold tracking-tight tabular-nums md:text-3xl">
                {formatMoney(order.cod_amount_vnd, order.currency)}
              </span>
              <span className="text-xs text-muted-foreground tabular-nums">
                Total {formatMoney(order.total_vnd, order.currency)}
                {order.prepaid_vnd > 0 && ` · Prepaid ${formatMoney(order.prepaid_vnd, order.currency)}`}
              </span>
            </div>
          </div>
        </FramePanel>
      </Frame>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)] lg:gap-8">
        <JourneyPanel order={order} />

        <div className="flex min-w-0 flex-col gap-6">
          <RiskPanel score={order.current_score ?? null} currency={order.currency ?? 'VND'} />
          <DecisionPanel
            order={order}
            onAcceptSuggestion={actions.onAcceptSuggestion}
            acceptingSuggestion={actions.acceptingSuggestion}
          />
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
        <FrameTitle className="text-base">Order journey</FrameTitle>
      </FrameHeader>
      <FramePanel className="flex flex-col gap-5">
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground">No events yet.</p>
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
                          Reason: {event.reason}
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
              Next step
            </span>
            <p className="flex items-center gap-1.5 text-sm">
              <ArrowRightIcon className="size-3.5 text-muted-foreground" aria-hidden="true" />
              {DECISION_ACTION_LABELS[next]}
              {order.decision?.next_action_at && (
                <span className="text-muted-foreground">
                  {' '}
                  if no response by {formatDateTime(order.decision.next_action_at)}
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
    system: 'System',
    engine: 'Decision engine',
    ai_call: 'AI call',
    buyer: 'Buyer',
    carrier: 'Carrier',
  }
  return known[actor] ?? actor
}

// ── Risk ──

function RiskPanel({ score, currency }: { score: RiskScore | null; currency: string }) {
  if (!score) {
    return (
      <PanelFrame eyebrow="Delivery refusal risk" title="Not scored yet">
        <p className="text-sm text-muted-foreground">New order: scoring in progress.</p>
      </PanelFrame>
    )
  }
  if (score.status === 'skipped') {
    return (
      <PanelFrame eyebrow="Delivery refusal risk" title="Scoring skipped">
        <p className="text-sm text-muted-foreground">
          {score.skipped_reason ? HARD_RULE_LABELS[score.skipped_reason] : 'Order needs no scoring'}: the
          buyer is not contacted.
        </p>
      </PanelFrame>
    )
  }

  const signals = score.top_signals ?? []
  const maxContribution = Math.max(0.01, ...signals.map((s) => Math.abs(s.contribution)))

  return (
    <PanelFrame
      eyebrow="Delivery refusal risk"
      title={
        <span className="flex flex-wrap items-center gap-2">
          <span className="tabular-nums">{score.risk_score}/100</span>
          {score.tier && <TierBadge tier={score.tier} />}
        </span>
      }
    >
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Metric
          label="Failed delivery probability"
          value={score.probability != null ? formatPercent(score.probability, 1) : '—'}
          estimated
        />
        <Metric
          label="Expected loss"
          value={score.expected_loss_vnd != null ? formatMoney(score.expected_loss_vnd, currency) : '—'}
          estimated
        />
        <Metric
          label="Cost of one failed delivery"
          value={formatMoney(score.failed_delivery_cost_vnd, currency)}
        />
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
          <h3 className="text-sm font-medium">Reasons</h3>
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
          <h3 className="text-sm font-medium">Top contributing signals</h3>
          <ul className="flex flex-col gap-2.5">
            {signals.map((signal) => (
              <SignalRow key={signal.key} signal={signal} max={maxContribution} currency={currency} />
            ))}
          </ul>
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        Model {score.model_version ?? '—'} · scored {formatDateTime(score.scored_at)}. The model and the
        decision engine set the score and the action; Gemini only writes the reasons.
      </p>
    </PanelFrame>
  )
}

function SignalRow({ signal, max, currency }: { signal: Signal; max: number; currency: string }) {
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
          {formatSignalValue(signal, currency)}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted" aria-hidden="true">
        <div
          className={cn('h-full rounded-full', raises ? 'bg-destructive' : 'bg-success')}
          style={{ width }}
        />
      </div>
      <span className="sr-only">{raises ? 'Raises risk' : 'Lowers risk'}</span>
    </li>
  )
}

function formatSignalValue({ key, value }: Signal, currency: string): string {
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number' && key === 'cod_amount_vnd') return formatMoney(value, currency)
  return String(value)
}

// ── Decision ──

function DecisionPanel({
  order,
  onAcceptSuggestion,
  acceptingSuggestion,
}: {
  order: OrderDetail
  onAcceptSuggestion?: () => void
  acceptingSuggestion?: boolean
}) {
  const decision = order.decision
  if (!decision) {
    return (
      <PanelFrame eyebrow="Decision" title="No decision yet">
        <p className="text-sm text-muted-foreground">The decision is made right after scoring.</p>
      </PanelFrame>
    )
  }
  return (
    <PanelFrame
      eyebrow="Decision"
      title={
        <span className="flex flex-wrap items-center gap-2">
          {DECISION_ACTION_LABELS[decision.action]}
          <Badge variant={decision.decided_by === 'staff' ? 'warning-outline' : 'outline'}>
            {decision.decided_by === 'staff' ? 'Staff decision' : 'Decision engine'}
          </Badge>
        </span>
      }
    >
      {order.random_test && (
        <p className="rounded-lg bg-info/10 p-3 text-sm">
          <span className="font-medium">Random test:</span> this action was picked at random among the actions
          this risk tier allows, so COD Guard can measure what each action prevents. Turn random tests off in
          Settings → Automation.
        </p>
      )}
      {order.review_reason && !decision.suggested_action && (
        <p className="rounded-lg bg-warning/10 p-3 text-sm">
          <span className="font-medium">Why it is in review:</span>{' '}
          {REVIEW_REASON_LABELS[order.review_reason]}
          {order.contact_summary && (
            <span className="text-muted-foreground"> · AI call: {order.contact_summary}</span>
          )}
        </p>
      )}
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Metric label="Decided at" value={formatDateTime(decision.decided_at)} />
        <Metric label="Policy" value={`Version ${decision.policy_version}`} />
        <Metric
          label="Expected loss / contact cost"
          value={`${decision.expected_loss_vnd != null ? formatMoney(decision.expected_loss_vnd, order.currency) : '—'} / ${
            decision.contact_cost_vnd != null ? formatMoney(decision.contact_cost_vnd, order.currency) : '—'
          }`}
          estimated
        />
      </dl>
      {decision.suggested_action && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-primary/5 p-3 text-sm">
          <p>
            <span className="font-medium">
              Suggested: {DECISION_ACTION_LABELS[decision.suggested_action]}.
            </span>{' '}
            Automation is off for this contact, so it waits for you. Accept it, or choose another action.
          </p>
          {onAcceptSuggestion && (
            <Button size="sm" onClick={onAcceptSuggestion} disabled={acceptingSuggestion}>
              {acceptingSuggestion && <Spinner data-icon="inline-start" />}
              Accept suggestion
            </Button>
          )}
        </div>
      )}
      {(decision.block_reasons?.length ?? 0) > 0 && (
        <div className="flex flex-col gap-1.5">
          <h3 className="text-sm font-medium">Not contacted because</h3>
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
    <PanelFrame
      eyebrow="Contact history"
      title={`${contacts.length} ${contacts.length === 1 ? 'contact' : 'contacts'}`}
    >
      {contacts.length === 0 ? (
        <p className="text-sm text-muted-foreground">Buyer not contacted yet.</p>
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
                        {call && ` · attempt ${call.attempt}`}
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
                        Link expires {formatDateTime(contact.link_expires_at)}
                      </span>
                    )}
                    <Button
                      variant="link"
                      size="sm"
                      className="h-auto p-0"
                      onClick={() => onPreviewMessage(contact)}
                    >
                      View sent message
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
  if (contact.responded_at) return <Badge variant="success-outline">Responded</Badge>
  return <Badge variant="outline">No response yet</Badge>
}

function CallSummary({ call }: { call: Call }) {
  return (
    <div className="flex flex-col gap-1 rounded-md bg-muted/50 p-3 text-sm">
      <p>{call.summary_vi}</p>
      {(call.changes?.length ?? 0) > 0 && (
        <ul className="text-xs text-muted-foreground">
          {call.changes!.map((change) => (
            <li key={`${change.field}-${change.new_value}`}>Change: {change.new_value}</li>
          ))}
        </ul>
      )}
      {call.buyer_requests && <p className="text-xs text-muted-foreground">Request: {call.buyer_requests}</p>}
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
        <span className="text-xs font-medium tracking-[0.16em] text-muted-foreground uppercase">Items</span>
        <FrameTitle className="text-base">
          {order.items.length} {order.items.length === 1 ? 'item' : 'items'}
        </FrameTitle>
      </FrameHeader>
      <FramePanel className="flex flex-col gap-6">
        <div role="list" aria-label="Items in the order" className="flex flex-col gap-3">
          {order.items.map((item, i) => (
            <article key={`${item.name}-${i}`} role="listitem" className="flex min-w-0 items-start gap-3">
              <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                <h3 className="min-w-0 truncate text-sm leading-snug font-medium">{item.name}</h3>
                <p className="text-xs text-muted-foreground">
                  {[item.variant, `Qty ${item.quantity}`, item.sku].filter(Boolean).join(' · ')}
                </p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-0.5 text-sm tabular-nums">
                <span className="font-semibold">
                  {formatMoney(item.quantity * item.unit_price_vnd, order.currency)}
                </span>
                {item.quantity > 1 && (
                  <span className="text-xs text-muted-foreground">
                    {formatMoney(item.unit_price_vnd, order.currency)} each
                  </span>
                )}
              </div>
            </article>
          ))}
        </div>

        <Separator />

        <dl className="flex flex-col gap-1.5 self-end sm:min-w-72">
          <SummaryRow label="Subtotal" value={formatMoney(subtotal, order.currency)} />
          <SummaryRow label="Shipping" value={formatMoney(order.shipping_fee_vnd, order.currency)} />
          {order.discount_vnd > 0 && (
            <SummaryRow
              label="Discount"
              value={`-${formatMoney(order.discount_vnd, order.currency)}`}
              tone="success"
            />
          )}
          <SummaryRow label="Total" value={formatMoney(order.total_vnd, order.currency)} />
          {order.prepaid_vnd > 0 && (
            <SummaryRow
              label="Prepaid"
              value={`-${formatMoney(order.prepaid_vnd, order.currency)}`}
              tone="success"
            />
          )}
          <Separator className="my-1" />
          <SummaryRow
            label="COD to collect"
            value={formatMoney(order.cod_amount_vnd, order.currency)}
            strong
          />
        </dl>
      </FramePanel>
    </Frame>
  )
}

function PartiesPanel({ order }: { order: OrderDetail }) {
  return (
    <Frame>
      <FramePanel className="grid grid-cols-1 gap-5 sm:grid-cols-3">
        <PartyBlock label="Buyer">
          <p className="font-medium">{order.buyer_name}</p>
          <p className="text-muted-foreground tabular-nums">{order.buyer_phone}</p>
        </PartyBlock>
        <PartyBlock label={order.is_gift ? 'Recipient (gift order)' : 'Recipient'}>
          <p className="font-medium">{order.recipient_name ?? order.buyer_name}</p>
          {order.is_gift && (
            <p className="text-xs text-muted-foreground">
              Verified with the buyer only; the recipient is never contacted.
            </p>
          )}
        </PartyBlock>
        <PartyBlock label="Deliver to">
          <p className="text-muted-foreground">{order.address.raw}</p>
          {order.note && <p className="text-xs text-muted-foreground">Note: {order.note}</p>}
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
    <PanelFrame eyebrow="Score history" title={`${runs.length} ${runs.length === 1 ? 'run' : 'runs'}`}>
      <ul className="flex flex-col divide-y text-sm">
        {runs.map((run) => (
          <li key={run.id} className="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0">
            <span className="text-muted-foreground tabular-nums">{formatDateTime(run.scored_at)}</span>
            <span className="flex items-center gap-2">
              {run.status === 'skipped' ? (
                <span className="text-muted-foreground">Skipped</span>
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
        {estimated && <span className="ms-1 text-[10px] tracking-wide uppercase">(estimated)</span>}
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
