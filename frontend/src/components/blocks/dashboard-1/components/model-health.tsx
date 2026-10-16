import { CheckCircle2Icon, RefreshCwIcon, TriangleAlertIcon } from 'lucide-react'

import type { ModelHealth } from '@/api/gen'
import { Badge } from '@/components/reui/badge'
import { Button } from '@/components/ui/button'
import { Frame, FrameDescription, FrameHeader, FramePanel, FrameTitle } from '@/components/ui/frame'
import { Spinner } from '@/components/ui/spinner'
import { COUNTRY_LABELS, formatDateTime } from '@/lib/labels'

// The risk model's health in words a shop owner understands (GET /dashboard/model-health), and the
// Update model button (owner only). "Update" = the model learns again from orders with a result.

function Status({ health }: { health: ModelHealth }) {
  if (health.updating)
    return (
      <Badge variant="info-light" className="gap-1">
        <Spinner className="size-3" /> Updating…
      </Badge>
    )
  if (health.status === 'up_to_date')
    return (
      <Badge variant="success-light" className="gap-1">
        <CheckCircle2Icon className="size-3" aria-hidden="true" /> Up to date
      </Badge>
    )
  if (health.status === 'update_recommended')
    return (
      <Badge variant="warning-light" className="gap-1">
        <TriangleAlertIcon className="size-3" aria-hidden="true" /> Update recommended
      </Badge>
    )
  return <Badge variant="secondary">Not trained yet</Badge>
}

export function ModelHealthCard({
  health,
  canUpdate,
  isStarting,
  onUpdate,
}: {
  health: ModelHealth
  canUpdate: boolean
  isStarting: boolean
  onUpdate: () => void
}) {
  const country = COUNTRY_LABELS[health.country] ?? health.country
  return (
    <Frame className="w-full">
      <FrameHeader className="flex-row items-start justify-between gap-3 px-2! py-2.5!">
        <div className="flex flex-col gap-1">
          <FrameTitle className="flex flex-wrap items-center gap-2">
            Risk model · {country}
            <Status health={health} />
          </FrameTitle>
          <FrameDescription>
            {health.trained_at
              ? `Last learned ${formatDateTime(health.trained_at)} from ${(health.training_orders ?? 0).toLocaleString('en-US')} orders.`
              : 'It learns from orders that have a delivery result.'}{' '}
            {health.checked_at && `Checked every night, last on ${formatDateTime(health.checked_at)}.`}
          </FrameDescription>
        </div>
        {canUpdate && health.status !== 'no_model' && (
          <Button size="sm" onClick={onUpdate} disabled={health.updating || isStarting}>
            {isStarting ? <Spinner data-icon="inline-start" /> : <RefreshCwIcon aria-hidden="true" />}
            Update risk model
          </Button>
        )}
      </FrameHeader>
      <FramePanel className="flex flex-col gap-2 text-sm">
        {health.lift_top20 != null && (
          <p>
            Among the orders it flags as riskiest, it finds{' '}
            <span className="font-semibold">{health.lift_top20.toFixed(1)}×</span> more failed deliveries than
            picking orders at random.{' '}
            <Badge variant="info-light" size="sm">
              estimated
            </Badge>
          </p>
        )}
        {health.new_outcomes != null && (
          <p className="text-muted-foreground">
            {health.new_outcomes.toLocaleString('en-US')} orders got a delivery result since it last learned.
          </p>
        )}
        {(health.reasons?.length ?? 0) > 0 && health.status === 'update_recommended' && (
          <ul className="list-disc ps-5 text-muted-foreground">
            {health.reasons?.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}
        <p className="text-xs text-muted-foreground">
          Updating takes about 2 minutes. The current model keeps working meanwhile, and the new one is used
          only if it is at least as good.
        </p>
      </FramePanel>
    </Frame>
  )
}
