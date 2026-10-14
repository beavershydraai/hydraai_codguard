import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'

import type { OrderDetail } from '@/api/gen'
import { updateOrderMutation } from '@/api/gen/@tanstack/react-query.gen'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { invalidate, problemMessage } from '@/lib/api'

/** Edits an order before it ships; the backend rescores it (E4.1). */
export function EditOrderSheet({
  order,
  open,
  onOpenChange,
}: {
  order: OrderDetail
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState(() => initial(order))
  const mutation = useMutation({
    ...updateOrderMutation(),
    onSuccess: (updated) => {
      toast.success('Saved and rescored', {
        description: updated.risk_score != null ? `New score: ${updated.risk_score}/100` : undefined,
      })
      void invalidate(queryClient, 'getOrder', 'listOrders')
      onOpenChange(false)
    },
  })
  const set = (key: keyof ReturnType<typeof initial>) => (event: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: event.target.value }))

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (next) setForm(initial(order))
        onOpenChange(next)
      }}
    >
      <SheetContent className="flex w-full flex-col sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Edit order {order.external_id ?? order.id}</SheetTitle>
          <SheetDescription>
            Saving rescores the order. Orders that have shipped can no longer be edited.
          </SheetDescription>
        </SheetHeader>
        <form
          id="edit-order-form"
          className="flex-1 overflow-y-auto px-4"
          onSubmit={(event) => {
            event.preventDefault()
            mutation.mutate({
              path: { order_id: order.id },
              body: {
                buyer_name: form.buyer_name.trim(),
                buyer_phone: form.buyer_phone.trim(),
                recipient_name: form.recipient_name.trim() || null,
                address: { raw: form.address.trim() },
                prepaid_vnd: Number(form.prepaid) || 0,
                note: form.note.trim() || null,
              },
            })
          }}
        >
          <FieldGroup className="gap-4">
            <Field>
              <FieldLabel htmlFor="edit-buyer">Buyer name</FieldLabel>
              <Input id="edit-buyer" value={form.buyer_name} onChange={set('buyer_name')} required />
            </Field>
            <Field>
              <FieldLabel htmlFor="edit-phone">Phone number</FieldLabel>
              <Input
                id="edit-phone"
                value={form.buyer_phone}
                onChange={set('buyer_phone')}
                inputMode="tel"
                required
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="edit-recipient">Recipient</FieldLabel>
              <Input id="edit-recipient" value={form.recipient_name} onChange={set('recipient_name')} />
              <FieldDescription>Leave empty if the buyer receives the order.</FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor="edit-address">Delivery address</FieldLabel>
              <Textarea
                id="edit-address"
                value={form.address}
                onChange={set('address')}
                required
                minLength={3}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="edit-prepaid">Prepaid (₫)</FieldLabel>
              <Input id="edit-prepaid" value={form.prepaid} onChange={set('prepaid')} inputMode="numeric" />
              <FieldDescription>
                Raising the prepaid amount lowers the amount left to collect.
              </FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor="edit-note">Note</FieldLabel>
              <Textarea id="edit-note" value={form.note} onChange={set('note')} />
            </Field>
          </FieldGroup>
          {mutation.isError && (
            <Alert variant="destructive" className="mt-4">
              <AlertDescription>{problemMessage(mutation.error)}</AlertDescription>
            </Alert>
          )}
        </form>
        <SheetFooter className="flex-row justify-end">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" form="edit-order-form" disabled={mutation.isPending}>
            {mutation.isPending && <Spinner data-icon="inline-start" />}
            Save and rescore
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}

function initial(order: OrderDetail) {
  return {
    buyer_name: order.buyer_name,
    buyer_phone: order.buyer_phone,
    recipient_name: order.recipient_name ?? '',
    address: order.address.raw,
    prepaid: String(order.prepaid_vnd),
    note: order.note ?? '',
  }
}
