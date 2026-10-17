import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { ArrowRightIcon, PhoneCallIcon, ShieldAlertIcon } from 'lucide-react'

import type { OrderSummary } from '@/api/gen'
import { getOrderOptions } from '@/api/gen/@tanstack/react-query.gen'
import { Badge } from '@/components/reui/badge'
import { buttonVariants } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { CALL_OUTCOME_LABELS, DECISION_ACTION_LABELS } from '@/lib/labels'

// What an expanded review row shows (ReUI c-data-grid-8): the order's risk reasons and its last AI
// call, read from the order itself only when the row opens, so the queue stays one request.

export function ReviewDetails({ order }: { order: OrderSummary }) {
  const { data, isPending, error } = useQuery(getOrderOptions({ path: { order_id: order.id } }))
  const reasons = data?.current_score?.reasons ?? []
  const call = data?.calls?.findLast((c) => c.status === 'completed' || c.summary_vi)

  return (
    <div className="grid gap-4 bg-muted/25 px-5 py-4 text-sm @2xl:grid-cols-[1fr_1fr_auto]">
      <section className="flex flex-col gap-1.5">
        <h3 className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <ShieldAlertIcon className="size-3.5" aria-hidden="true" />
          Why it is risky
        </h3>
        {isPending ? (
          <Lines />
        ) : error ? (
          <p className="text-muted-foreground">Could not load the order.</p>
        ) : reasons.length ? (
          <ul className="flex list-disc flex-col gap-1 ps-4">
            {reasons.map((r) => (
              <li key={r.text_vi}>{r.text_vi}</li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground">No reasons: the order was not scored.</p>
        )}
      </section>

      <section className="flex flex-col gap-1.5">
        <h3 className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <PhoneCallIcon className="size-3.5" aria-hidden="true" />
          Last AI call
        </h3>
        {isPending ? (
          <Lines />
        ) : call ? (
          <>
            {call.outcome && (
              <Badge variant="outline" size="sm" className="w-fit">
                {CALL_OUTCOME_LABELS[call.outcome]}
              </Badge>
            )}
            <p>{call.summary_vi ?? 'No summary.'}</p>
            {call.buyer_requests && <p className="text-muted-foreground">Request: {call.buyer_requests}</p>}
            {(call.changes ?? []).map((change) => (
              <p key={`${change.field}-${change.new_value}`} className="text-muted-foreground">
                Change: {change.new_value}
              </p>
            ))}
          </>
        ) : (
          <p className="text-muted-foreground">No AI call yet.</p>
        )}
      </section>

      <div className="flex flex-col items-start gap-2 @2xl:items-end">
        {order.suggested_action && (
          <span className="text-xs text-muted-foreground">
            Suggested: {DECISION_ACTION_LABELS[order.suggested_action]}
          </span>
        )}
        <Link
          to="/orders/$orderId"
          params={{ orderId: order.id }}
          className={buttonVariants({ variant: 'outline', size: 'sm' })}
        >
          Open order
          <ArrowRightIcon data-icon="inline-end" aria-hidden="true" />
        </Link>
      </div>
    </div>
  )
}

function Lines() {
  return (
    <div className="flex flex-col gap-1.5">
      <Skeleton className="h-3.5 w-11/12" />
      <Skeleton className="h-3.5 w-3/4" />
    </div>
  )
}
