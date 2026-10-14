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
      toast.success(`Đã tạo đơn ${order.external_id ?? order.id}`, {
        description: order.tier ? `Rủi ro: ${order.risk_score}/100` : 'Đang chấm điểm…',
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
          <SheetTitle>Tạo đơn</SheetTitle>
          <SheetDescription>Đơn được chấm điểm và quyết định ngay sau khi tạo.</SheetDescription>
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
                <FieldLabel htmlFor="new-channel">Kênh bán</FieldLabel>
                <Select
                  value={form.channel}
                  onValueChange={(value) => setForm((f) => ({ ...f, channel: value as SalesChannel }))}
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
                <FieldLabel htmlFor="new-external">Mã đơn của shop</FieldLabel>
                <Input
                  id="new-external"
                  value={form.externalId}
                  onChange={set('externalId')}
                  placeholder="FB-2001"
                />
              </Field>
            </div>
            <Field>
              <FieldLabel htmlFor="new-buyer">Tên người mua</FieldLabel>
              <Input id="new-buyer" value={form.buyerName} onChange={set('buyerName')} required />
            </Field>
            <Field>
              <FieldLabel htmlFor="new-phone">Số điện thoại</FieldLabel>
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
              <FieldLabel htmlFor="new-address">Địa chỉ giao</FieldLabel>
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
              Đơn quà tặng (người nhận khác người mua)
            </Label>
            {form.gift && (
              <Field>
                <FieldLabel htmlFor="new-recipient">Tên người nhận</FieldLabel>
                <Input id="new-recipient" value={form.recipientName} onChange={set('recipientName')} />
                <FieldDescription>
                  COD Guard chỉ xác minh với người mua, không liên hệ người nhận.
                </FieldDescription>
              </Field>
            )}

            <FieldSeparator />
            <div className="flex flex-col gap-3">
              {lines.map((line, i) => (
                <div key={i} className="grid grid-cols-[1fr_5rem] gap-2 rounded-lg border p-3">
                  <Input
                    aria-label={`Sản phẩm ${i + 1}`}
                    placeholder="Tên sản phẩm"
                    value={line.name}
                    onChange={setLine(i, 'name')}
                    required={i === 0}
                  />
                  <Input
                    aria-label={`Số lượng ${i + 1}`}
                    inputMode="numeric"
                    value={line.quantity}
                    onChange={setLine(i, 'quantity')}
                  />
                  <Input
                    aria-label={`Phân loại ${i + 1}`}
                    placeholder="Màu / size"
                    value={line.variant}
                    onChange={setLine(i, 'variant')}
                  />
                  <div className="flex gap-1">
                    <Input
                      aria-label={`Đơn giá ${i + 1}`}
                      inputMode="numeric"
                      placeholder="Giá"
                      value={line.price}
                      onChange={setLine(i, 'price')}
                      required={i === 0}
                    />
                    {lines.length > 1 && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={`Bỏ sản phẩm ${i + 1}`}
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
                Thêm sản phẩm
              </Button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field>
                <FieldLabel htmlFor="new-shipping">Phí ship (₫)</FieldLabel>
                <Input
                  id="new-shipping"
                  inputMode="numeric"
                  value={form.shipping}
                  onChange={set('shipping')}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="new-prepaid">Đã trả trước (₫)</FieldLabel>
                <Input id="new-prepaid" inputMode="numeric" value={form.prepaid} onChange={set('prepaid')} />
              </Field>
            </div>
            <Field>
              <FieldLabel htmlFor="new-note">Ghi chú</FieldLabel>
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
            Thu hộ: {formatVnd(Math.max(total - num(form.prepaid), 0))}
          </span>
          <Button type="submit" form="create-order-form" disabled={mutation.isPending || items.length === 0}>
            {mutation.isPending && <Spinner data-icon="inline-start" />}
            Tạo và chấm điểm
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
