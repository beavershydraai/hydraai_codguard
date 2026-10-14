import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'

import type { DecisionAction, OrderDetail } from '@/api/gen'
import { overrideOrderMutation } from '@/api/gen/@tanstack/react-query.gen'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { invalidate, problemMessage } from '@/lib/api'
import { DECISION_ACTION_LABELS } from '@/lib/labels'

const HELP: Record<DecisionAction, string> = {
  ship_now: 'Ship right away, with no further contact.',
  send_confirmation_link: 'Send a link so the buyer can confirm or edit the order.',
  ai_call: 'An AI call asks the buyer to confirm.',
  require_deposit: 'Ask the buyer for a deposit before shipping.',
  hold_for_review: 'Hold the order for the shop to review later.',
  cancel: 'Cancel the order; nothing ships.',
}

/** Staff decision that replaces the engine's (E4.5). Who, when and why go to the audit log. */
export function OverrideDialog({
  order,
  open,
  onOpenChange,
  preset,
}: {
  order: OrderDetail
  open: boolean
  onOpenChange: (open: boolean) => void
  preset?: DecisionAction
}) {
  const queryClient = useQueryClient()
  const allowed = order.allowed_overrides ?? []
  const [action, setAction] = useState<DecisionAction | undefined>(preset)
  const [reason, setReason] = useState('')
  const mutation = useMutation({
    ...overrideOrderMutation(),
    onSuccess: () => {
      toast.success('Decision recorded', {
        description: `${DECISION_ACTION_LABELS[action!]} · ${reason.trim()}`,
      })
      void invalidate(queryClient, 'getOrder', 'listOrders')
      onOpenChange(false)
      setReason('')
    },
  })
  const valid = !!action && allowed.includes(action) && reason.trim().length >= 3

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (next) setAction(preset)
        onOpenChange(next)
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Override the system decision</DialogTitle>
          <DialogDescription>
            Order {order.external_id ?? order.id}. Who decided, when and why are recorded in the audit log.
          </DialogDescription>
        </DialogHeader>

        <form
          id="override-form"
          className="flex flex-col gap-5"
          onSubmit={(event) => {
            event.preventDefault()
            if (!valid) return
            mutation.mutate({
              path: { order_id: order.id },
              body: { action: action!, reason: reason.trim() },
            })
          }}
        >
          <RadioGroup
            value={action ?? ''}
            onValueChange={(value) => setAction(value as DecisionAction)}
            className="gap-2"
            aria-label="Action"
          >
            {allowed.map((value) => (
              <Label
                key={value}
                htmlFor={`override-${value}`}
                className="flex cursor-pointer items-start gap-3 rounded-lg border p-3 font-normal has-data-[state=checked]:border-primary has-data-[state=checked]:bg-primary/5"
              >
                <RadioGroupItem id={`override-${value}`} value={value} className="mt-0.5" />
                <span className="flex flex-col gap-0.5">
                  <span className="font-medium">{DECISION_ACTION_LABELS[value]}</span>
                  <span className="text-xs text-muted-foreground">{HELP[value]}</span>
                </span>
              </Label>
            ))}
          </RadioGroup>

          <Field>
            <FieldLabel htmlFor="override-reason">Reason</FieldLabel>
            <Textarea
              id="override-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="e.g. Regular buyer, already confirmed on Zalo."
              maxLength={500}
              required
            />
            <FieldDescription>Required, at least 3 characters.</FieldDescription>
          </Field>

          {mutation.isError && (
            <Alert variant="destructive">
              <AlertDescription>{problemMessage(mutation.error)}</AlertDescription>
            </Alert>
          )}
        </form>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Back
          </Button>
          <Button type="submit" form="override-form" disabled={!valid || mutation.isPending}>
            {mutation.isPending && <Spinner data-icon="inline-start" />}
            Record decision
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
