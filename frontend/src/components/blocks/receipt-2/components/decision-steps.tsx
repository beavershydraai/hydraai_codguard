import { CircleCheckIcon, CircleSlashIcon, CircleXIcon, HandIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import type { OrderDetail } from '@/api/gen'
import { Badge } from '@/components/reui/badge'
import { TierBadge } from '@/components/tier-badge'
import { Button } from '@/components/ui/button'
import { Marker, MarkerContent, MarkerIcon } from '@/components/ui/marker'
import { Spinner } from '@/components/ui/spinner'
import {
  BLOCK_REASON_LABELS,
  CALL_OUTCOME_LABELS,
  CALL_STATUS_LABELS,
  CONTACT_CHANNEL_LABELS,
  DECISION_ACTION_LABELS,
  formatDateTime,
  HARD_RULE_LABELS,
  REVIEW_REASON_LABELS,
  SALES_CHANNEL_LABELS,
} from '@/lib/labels'
import { cn } from '@/lib/utils'

// The order's run through the pipeline (load → score → assess → decide → act), as the ReUI
// agent-activity-1 run console: finished steps in muted rows, the step that waits for the shop in
// a band with its action (the suggested contact to accept), and what comes next in dashed rings.
// Everything is read from the order; nothing here decides.

type StepState = 'done' | 'skipped' | 'failed' | 'live' | 'blocked' | 'queued'

type Step = {
  key: string
  state: StepState
  label: ReactNode
  note?: ReactNode
  at?: string | null
  badge?: {
    variant: 'info-light' | 'warning-light' | 'destructive-light' | 'success-light' | 'secondary'
    label: string
  }
  action?: ReactNode
}

const ACTIVE_CALL = new Set(['queued', 'dialing', 'in_progress'])

function stepsFor(order: OrderDetail, onAccept: (() => void) | undefined, accepting: boolean): Step[] {
  const steps: Step[] = []
  const score = order.current_score
  const decision = order.decision

  steps.push({
    key: 'received',
    state: 'done',
    label: `Order received from ${SALES_CHANNEL_LABELS[order.channel]}`,
    at: order.placed_at,
  })

  if (!score) {
    steps.push({ key: 'score', state: 'live', label: 'Scoring the order' })
    return steps
  }
  if (score.status === 'skipped') {
    steps.push({
      key: 'score',
      state: 'skipped',
      label: 'Scoring skipped',
      note: score.skipped_reason ? HARD_RULE_LABELS[score.skipped_reason] : undefined,
      at: score.scored_at,
    })
  } else {
    steps.push({
      key: 'score',
      state: 'done',
      label: (
        <span className="flex flex-wrap items-center gap-1.5">
          Scored {score.risk_score}/100 {score.tier && <TierBadge tier={score.tier} />}
        </span>
      ),
      note: score.hard_rules?.length
        ? `Hard rule: ${score.hard_rules.map((r) => HARD_RULE_LABELS[r]).join(', ')}`
        : undefined,
      at: score.scored_at,
    })
    const reasons = score.reasons?.length ?? 0
    steps.push({
      key: 'assess',
      state: reasons ? 'done' : 'skipped',
      label: reasons
        ? `Risk explained in ${reasons} ${reasons === 1 ? 'reason' : 'reasons'}`
        : 'No reasons kept',
      note: reasons
        ? 'Each reason cites evidence on the order; the AI never sets the score or the action.'
        : undefined,
    })
  }

  if (!decision) {
    steps.push({ key: 'decide', state: 'live', label: 'Picking the action' })
    return steps
  }
  const picked = decision.suggested_action ?? decision.action
  const blocked = (decision.block_reasons ?? []).filter((r) => r !== 'manual_approval')
  steps.push({
    key: 'decide',
    state: 'done',
    label: `${decision.decided_by === 'staff' ? 'Staff chose' : 'Engine picked'}: ${DECISION_ACTION_LABELS[picked]}`,
    badge: order.random_test
      ? { variant: 'info-light', label: 'Random test' }
      : decision.decided_by === 'staff'
        ? { variant: 'warning-light', label: 'Staff' }
        : undefined,
    note: order.random_test
      ? 'Picked at random among the actions this tier allows, so COD Guard learns what each prevents.'
      : blocked.length
        ? `Not contacted: ${blocked.map((r) => BLOCK_REASON_LABELS[r]).join(', ')}`
        : undefined,
    at: decision.decided_at,
  })

  if (decision.suggested_action) {
    steps.push({
      key: 'approve',
      state: 'blocked',
      label: `Suggested: ${DECISION_ACTION_LABELS[decision.suggested_action]}`,
      badge: { variant: 'success-light', label: 'Needs you' },
      note: 'Automation is off for this contact, so nothing reaches the buyer until you accept.',
      action: onAccept && (
        <Button size="sm" onClick={onAccept} disabled={accepting}>
          {accepting && <Spinner data-icon="inline-start" />}
          Accept
        </Button>
      ),
    })
  }

  const calls = new Map((order.calls ?? []).map((call) => [call.id, call]))
  for (const contact of [...(order.contacts ?? [])].sort((a, b) =>
    a.created_at.localeCompare(b.created_at),
  )) {
    const call = contact.call_id ? calls.get(contact.call_id) : undefined
    const live = !!call && ACTIVE_CALL.has(call.status)
    steps.push({
      key: contact.id,
      state: live ? 'live' : 'done',
      label: call ? `AI call, attempt ${call.attempt}` : `${CONTACT_CHANNEL_LABELS[contact.channel]} sent`,
      badge: call?.outcome
        ? { variant: 'secondary', label: CALL_OUTCOME_LABELS[call.outcome] }
        : call
          ? { variant: 'info-light', label: CALL_STATUS_LABELS[call.status] }
          : contact.responded_at
            ? { variant: 'success-light', label: 'Responded' }
            : undefined,
      note: call?.summary_vi ?? undefined,
      at: contact.created_at,
    })
  }

  switch (order.status) {
    case 'pending_review':
      if (!decision.suggested_action) {
        steps.push({
          key: 'review',
          state: 'blocked',
          label: order.review_reason
            ? REVIEW_REASON_LABELS[order.review_reason]
            : 'Held for a person to decide',
          badge: { variant: 'success-light', label: 'Needs you' },
          note: 'Approve, ask for a deposit or cancel with Override, or from the review queue.',
        })
      }
      break
    case 'awaiting_confirmation':
    case 'awaiting_deposit':
      // A call in progress is already the live row.
      if (steps.at(-1)?.state === 'live') break
      steps.push({
        key: 'wait',
        state: 'live',
        label: order.status === 'awaiting_deposit' ? 'Waiting for the deposit' : 'Waiting for the buyer',
      })
      break
    case 'cleared_to_ship':
    case 'shipped':
    case 'delivered':
      steps.push({
        key: 'final',
        state: 'done',
        label:
          order.status === 'cleared_to_ship'
            ? 'Cleared to ship'
            : order.status === 'shipped'
              ? 'Shipped'
              : 'Delivered',
      })
      break
    case 'delivery_failed':
      steps.push({ key: 'final', state: 'failed', label: 'Delivery failed' })
      break
    case 'cancelled':
      steps.push({ key: 'final', state: 'skipped', label: 'Cancelled' })
      break
  }

  if (decision.next_action) {
    steps.push({
      key: 'next',
      state: 'queued',
      label: `Then: ${DECISION_ACTION_LABELS[decision.next_action]}`,
      note: decision.next_action_at
        ? `If no response by ${formatDateTime(decision.next_action_at)}`
        : undefined,
    })
  }
  return steps
}

function DashedRing() {
  return <span className="size-4 rounded-full border border-dashed border-current" />
}

const GLYPH: Record<StepState, { icon: ReactNode; tone: string }> = {
  done: { icon: <CircleCheckIcon />, tone: 'text-muted-foreground' },
  skipped: { icon: <CircleSlashIcon />, tone: 'text-muted-foreground' },
  failed: { icon: <CircleXIcon />, tone: 'text-destructive' },
  live: { icon: <Spinner className="size-4" />, tone: 'text-foreground' },
  blocked: { icon: <HandIcon />, tone: 'text-success' },
  queued: { icon: <DashedRing />, tone: 'text-muted-foreground' },
}

export function DecisionSteps({
  order,
  onAcceptSuggestion,
  acceptingSuggestion = false,
}: {
  order: OrderDetail
  onAcceptSuggestion?: () => void
  acceptingSuggestion?: boolean
}) {
  const steps = stepsFor(order, onAcceptSuggestion, acceptingSuggestion)
  return (
    <ol className="-mx-(--frame-panel-px) flex flex-col" aria-label="How the order was handled">
      {steps.map((step) => {
        const band = step.state === 'blocked' || step.state === 'live'
        return (
          <li key={step.key}>
            <Marker
              role={band ? 'status' : undefined}
              className={cn(
                'items-start px-(--frame-panel-px) py-2',
                band && 'border-y border-border bg-muted/50 py-2.5',
              )}
            >
              <MarkerIcon
                className={cn('flex h-5 w-4 items-center justify-center self-start', GLYPH[step.state].tone)}
              >
                {GLYPH[step.state].icon}
              </MarkerIcon>
              <MarkerContent className="flex min-w-0 flex-1 flex-col gap-0.5 text-[13px]">
                <span className="flex min-h-5 flex-wrap items-center gap-x-2 gap-y-1 leading-5">
                  <span
                    className={cn(
                      step.state === 'queued' ? 'text-muted-foreground' : 'text-foreground',
                      step.state === 'skipped' && step.key === 'final' && 'line-through',
                      band && 'font-medium',
                    )}
                  >
                    {step.label}
                  </span>
                  {step.badge && (
                    <Badge variant={step.badge.variant} className="font-normal">
                      {step.badge.label}
                    </Badge>
                  )}
                </span>
                {step.note && <span className="text-xs leading-5 text-muted-foreground">{step.note}</span>}
              </MarkerContent>
              {step.action ? (
                <span className="shrink-0 self-center">{step.action}</span>
              ) : (
                step.at && (
                  <time
                    dateTime={step.at}
                    className="flex h-5 shrink-0 items-center self-start text-xs text-muted-foreground tabular-nums"
                  >
                    {formatDateTime(step.at)}
                  </time>
                )
              )}
            </Marker>
          </li>
        )
      })}
    </ol>
  )
}
