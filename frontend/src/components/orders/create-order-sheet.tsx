import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { PlusIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import type { OrderItem, SalesChannel } from '@/api/gen'
import { createOrderMutation } from '@/api/gen/@tanstack/react-query.gen'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSeparator } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
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
import { formatVnd, SALES_CHANNEL_LABELS } from '@/lib/labels'

type Line = { name: string; variant: string; quantity: string; price: string }
const EMPTY_LINE: Line = { name: '', variant: '', quantity: '1', price: '' }

/** Create one order by hand (POST /orders); scoring runs right after. */
export function CreateOrderSheet({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [form, setForm] = useState(initial)
  const [lines, setLines] = useState<Line[]>([{ ...EMPTY_LINE }])
  const mutation = useMutation({
    ...createOrderMutation(),
    onSuccess: (order) => {
      toast.success(`Order ${order.external_id ?? order.id} created`, {
        description: order.tier ? `Risk score: ${order.risk_score}/100` : 'Scoring…',
      })
      void invalidate(queryClient, 'listOrders', 'getDashboardSummary')
      onOpenChange(false)
      void navigate({ to: '/orders/$orderId', params: { orderId: order.id } })
    },
  })

  const set = (key: keyof ReturnType<typeof initial>) => (event: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: event.target.value }))
  const setLine = (index: number, key: keyof Line) => (event: { target: { value: string } }) =>
    setLines((current) =>
      current.map((line, i) => (i === index ? { ...line, [key]: event.target.value } : line)),
    )
  const num = (value: string) => Math.max(0, Math.round(Number(value.replace(/\D/g, '')) || 0))
  const items: OrderItem[] = lines
    .filter((l) => l.name.trim())
    .map((l) => ({
      name: l.name.trim(),
      variant: l.variant.trim() || null,
      quantity: Math.max(1, num(l.quantity)),
      unit_price_vnd: num(l.price),
    }))
  const total = items.reduce((s, i) => s + i.quantity * i.unit_price_vnd, 0) + num(form.shipping)

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (next) {
          setForm(initial())
          setLines([{ ...EMPTY_LINE }])
          mutation.reset()
        }
        onOpenChange(next)
      }}
    >
      <SheetContent className="flex w-full flex-col sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>Create order</SheetTitle>
          <SheetDescription>
            The order is scored and a decision is made right after it is created.
          </SheetDescription>
        </SheetHeader>
        <form
          id="create-order-form"
          className="flex-1 overflow-y-auto px-4"
          onSubmit={(event) => {
            event.preventDefault()
            mutation.mutate({
              body: {
                external_id: form.externalId.trim() || null,
                channel: form.channel,
                buyer_name: form.buyerName.trim(),
                buyer_phone: form.buyerPhone.trim(),
                is_gift: form.gift,
                recipient_name: form.gift ? form.recipientName.trim() || null : null,
                address: { raw: form.address.trim() },
                items,
                shipping_fee_vnd: num(form.shipping),
                prepaid_vnd: num(form.prepaid),
                placed_at: new Date().toISOString(),
                note: form.note.trim() || null,
              },
            })
          }}
        >
          <FieldGroup className="gap-4">
            <div className="grid grid-cols-2 gap-3">
              <Field>
                <FieldLabel htmlFor="new-channel">Sales channel</FieldLabel>
                <Select
                  items={SALES_CHANNEL_LABELS}
                  value={form.channel}
                  onValueChange={(value) => value !== null && setForm((f) => ({ ...f, channel: value }))}
                >
                  <SelectTrigger id="new-channel" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {(Object.keys(SALES_CHANNEL_LABELS) as SalesChannel[]).map((c) => (
                        <SelectItem key={c} value={c}>
                          {SALES_CHANNEL_LABELS[c]}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
              <Field>
                <FieldLabel htmlFor="new-external">Shop's order ID</FieldLabel>
                <Input
                  id="new-external"
                  value={form.externalId}
                  onChange={set('externalId')}
                  placeholder="FB-2001"
                />
              </Field>
            </div>
            <Field>
              <FieldLabel htmlFor="new-buyer">Buyer name</FieldLabel>
              <Input id="new-buyer" value={form.buyerName} onChange={set('buyerName')} required />
            </Field>
            <Field>
              <FieldLabel htmlFor="new-phone">Phone number</FieldLabel>
              <Input
                id="new-phone"
                value={form.buyerPhone}
                onChange={set('buyerPhone')}
                inputMode="tel"
                placeholder="09…"
                required
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="new-address">Delivery address</FieldLabel>
              <Textarea
                id="new-address"
                value={form.address}
                onChange={set('address')}
                required
                minLength={3}
              />
            </Field>
            <Label className="flex items-center gap-2 font-normal">
              <Checkbox
                checked={form.gift}
                onCheckedChange={(checked) => setForm((f) => ({ ...f, gift: checked === true }))}
              />
              Gift order (recipient is not the buyer)
            </Label>
            {form.gift && (
              <Field>
                <FieldLabel htmlFor="new-recipient">Recipient name</FieldLabel>
                <Input id="new-recipient" value={form.recipientName} onChange={set('recipientName')} />
                <FieldDescription>
                  COD Guard verifies with the buyer only and never contacts the recipient.
                </FieldDescription>
              </Field>
            )}

            <FieldSeparator />
            <div className="flex flex-col gap-3">
              {lines.map((line, i) => (
                <div key={i} className="grid grid-cols-[1fr_5rem] gap-2 rounded-lg border p-3">
                  <Input
                    aria-label={`Item ${i + 1}`}
                    placeholder="Item name"
                    value={line.name}
                    onChange={setLine(i, 'name')}
                    required={i === 0}
                  />
                  <Input
                    aria-label={`Quantity ${i + 1}`}
                    inputMode="numeric"
                    value={line.quantity}
                    onChange={setLine(i, 'quantity')}
                  />
                  <Input
                    aria-label={`Variant ${i + 1}`}
                    placeholder="Color / size"
                    value={line.variant}
                    onChange={setLine(i, 'variant')}
                  />
                  <div className="flex gap-1">
                    <Input
                      aria-label={`Unit price ${i + 1}`}
                      inputMode="numeric"
                      placeholder="Price"
                      value={line.price}
                      onChange={setLine(i, 'price')}
                      required={i === 0}
                    />
                    {lines.length > 1 && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={`Remove item ${i + 1}`}
                        onClick={() => setLines((c) => c.filter((_, j) => j !== i))}
                      >
                        <Trash2Icon />
                      </Button>
                    )}
                  </div>
                </div>
              ))}
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="self-start"
                onClick={() => setLines((c) => [...c, { ...EMPTY_LINE }])}
              >
                <PlusIcon aria-hidden="true" />
                Add item
              </Button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field>
                <FieldLabel htmlFor="new-shipping">Shipping fee (₫)</FieldLabel>
                <Input
                  id="new-shipping"
                  inputMode="numeric"
                  value={form.shipping}
                  onChange={set('shipping')}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="new-prepaid">Prepaid (₫)</FieldLabel>
                <Input id="new-prepaid" inputMode="numeric" value={form.prepaid} onChange={set('prepaid')} />
              </Field>
            </div>
            <Field>
              <FieldLabel htmlFor="new-note">Note</FieldLabel>
              <Textarea id="new-note" value={form.note} onChange={set('note')} />
            </Field>
          </FieldGroup>
          {mutation.isError && (
            <Alert variant="destructive" className="mt-4">
              <AlertDescription>{problemMessage(mutation.error)}</AlertDescription>
            </Alert>
          )}
        </form>
        <SheetFooter className="flex-row items-center justify-between">
          <span className="text-sm text-muted-foreground tabular-nums">
            To collect: {formatVnd(Math.max(total - num(form.prepaid), 0))}
          </span>
          <Button type="submit" form="create-order-form" disabled={mutation.isPending || items.length === 0}>
            {mutation.isPending && <Spinner data-icon="inline-start" />}
            Create and score
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}

function initial() {
  return {
    channel: 'facebook' as SalesChannel,
    externalId: '',
    buyerName: '',
    buyerPhone: '',
    address: '',
    gift: false,
    recipientName: '',
    shipping: '30000',
    prepaid: '0',
    note: '',
  }
}
