import {
  CircleCheckIcon,
  CircleXIcon,
  ClockIcon,
  type LucideIcon,
  MapPinIcon,
  ShieldAlertIcon,
  ShieldCheckIcon,
} from 'lucide-react'
import { useState } from 'react'

import type { BuyerAction, BuyerOrderView, BuyerResponseResult } from '@/api/gen'
import { Badge } from '@/components/reui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field'
import { Item, ItemMedia } from '@/components/ui/item'
import { Separator } from '@/components/ui/separator'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { BUYER_ACTION_LABELS, formatDateTime, formatVnd } from '@/lib/labels'

// Buyer confirmation page (E6.1): no login, the link token is the credential, personal data is
// partly masked and the link expires after 48 hours. Laid out like ReUI receipt-6: a hero card,
// the items, then a grid of equal-weight action tiles.

const TILES: { action: BuyerAction; icon: LucideIcon; description: string; tone?: string }[] = [
  { action: 'confirm', icon: CircleCheckIcon, description: 'Đúng đơn, giao cho tôi', tone: 'text-success' },
  { action: 'edit_address', icon: MapPinIcon, description: 'Giao tới chỗ khác' },
  { action: 'cancel', icon: CircleXIcon, description: 'Tôi không cần nữa' },
  { action: 'not_ordered', icon: ShieldAlertIcon, description: 'Có người đặt giả', tone: 'text-destructive' },
]

export function ConfirmationPage({
  view,
  pending,
  error,
  result,
  onRespond,
}: {
  view: BuyerOrderView
  pending: boolean
  error: string | null
  result: BuyerResponseResult | null
  onRespond: (action: BuyerAction, newAddress?: string) => void
}) {
  const [step, setStep] = useState<BuyerAction | null>(null)
  const [address, setAddress] = useState('')
  const answered = result?.action ?? view.responded_action ?? null

  return (
    <ConfirmationShell shopName={view.shop_name}>
      {/* Hero */}
      <Card>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm text-muted-foreground">Đơn {view.order_ref}</span>
            <Badge variant="outline" className="gap-1">
              <ClockIcon aria-hidden="true" className="size-3" />
              Hết hạn {formatDateTime(view.expires_at)}
            </Badge>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-xs font-medium tracking-[0.16em] text-muted-foreground uppercase">
              Số tiền trả khi nhận hàng
            </span>
            <span className="text-3xl leading-none font-semibold tracking-tight tabular-nums">
              {formatVnd(view.cod_amount_vnd)}
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Items and delivery */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Thông tin đơn</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <ul className="flex flex-col gap-2">
            {view.items.map((item, i) => (
              <li key={`${item.name}-${i}`} className="flex items-start justify-between gap-3 text-sm">
                <span>
                  {item.name}
                  {item.variant && <span className="text-muted-foreground"> · {item.variant}</span>}
                </span>
                <span className="shrink-0 text-muted-foreground tabular-nums">x{item.quantity}</span>
              </li>
            ))}
          </ul>
          <Separator />
          <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-xs text-muted-foreground">Người nhận</dt>
              <dd className="font-medium">{view.recipient_name_masked}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Số điện thoại</dt>
              <dd className="font-medium tabular-nums">{view.phone_masked}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Giao tới</dt>
              <dd className="font-medium">{view.address_masked}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {answered ? (
        <DoneCard action={answered} message={result?.message_vi} />
      ) : step === 'edit_address' ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Địa chỉ giao mới</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="flex flex-col gap-4"
              onSubmit={(event) => {
                event.preventDefault()
                if (address.trim().length >= 10) onRespond('edit_address', address.trim())
              }}
            >
              <Field>
                <FieldLabel htmlFor="new-address">Số nhà, đường, phường/xã, tỉnh/thành phố</FieldLabel>
                <Textarea
                  id="new-address"
                  value={address}
                  onChange={(event) => setAddress(event.target.value)}
                  placeholder="Ví dụ: Số 12 ngõ 34, phường Cầu Giấy, Hà Nội"
                  autoFocus
                  required
                  minLength={10}
                />
                <FieldDescription>Ghi đầy đủ số nhà để shipper tìm được nhanh.</FieldDescription>
              </Field>
              <div className="flex gap-2">
                <Button type="submit" disabled={pending || address.trim().length < 10} className="flex-1">
                  {pending && <Spinner data-icon="inline-start" />}
                  Lưu địa chỉ và xác nhận
                </Button>
                <Button type="button" variant="outline" onClick={() => setStep(null)}>
                  Quay lại
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      ) : step === 'cancel' || step === 'not_ordered' ? (
        <Card>
          <CardContent className="flex flex-col gap-4">
            <p className="text-sm">
              {step === 'cancel'
                ? 'Bạn chắc chắn muốn hủy đơn này? Shop sẽ không gửi hàng.'
                : 'Bạn không đặt đơn này? Shop sẽ hủy đơn và số điện thoại này sẽ không bị liên hệ trong 30 ngày.'}
            </p>
            <div className="flex gap-2">
              <Button
                variant="destructive"
                className="flex-1"
                disabled={pending}
                onClick={() => onRespond(step)}
              >
                {pending && <Spinner data-icon="inline-start" />}
                {step === 'cancel' ? 'Hủy đơn' : 'Tôi không đặt đơn này'}
              </Button>
              <Button variant="outline" onClick={() => setStep(null)}>
                Quay lại
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div
          role="group"
          aria-label={`Trả lời cho đơn ${view.order_ref}`}
          className="grid grid-cols-2 gap-3 sm:grid-cols-4"
        >
          {TILES.filter((tile) => view.allowed_actions.includes(tile.action)).map(
            ({ action, icon: Icon, description, tone }) => (
              <Item
                key={action}
                variant="outline"
                asChild
                className="flex flex-col items-center gap-2 p-4 text-center transition-colors hover:bg-muted/60"
              >
                <button
                  type="button"
                  disabled={pending}
                  onClick={() => (action === 'confirm' ? onRespond('confirm') : setStep(action))}
                >
                  <Icon className={`size-5 ${tone ?? 'text-foreground'}`} aria-hidden="true" />
                  <div className="flex flex-col gap-0.5">
                    <span className="text-sm leading-snug font-medium">{BUYER_ACTION_LABELS[action]}</span>
                    <span className="text-xs leading-snug text-muted-foreground">{description}</span>
                  </div>
                </button>
              </Item>
            ),
          )}
        </div>
      )}

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
    </ConfirmationShell>
  )
}

function DoneCard({ action, message }: { action: BuyerAction; message?: string }) {
  const positive = action === 'confirm' || action === 'edit_address'
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-4 text-center">
        <Item variant="outline" className="size-12 justify-center p-0">
          <ItemMedia variant="icon" className="size-auto">
            {positive ? (
              <CircleCheckIcon className="size-6 text-success" aria-hidden="true" />
            ) : (
              <CircleXIcon className="size-6 text-muted-foreground" aria-hidden="true" />
            )}
          </ItemMedia>
        </Item>
        <p className="font-medium">Bạn đã chọn: {BUYER_ACTION_LABELS[action]}</p>
        <p className="text-sm text-muted-foreground">
          {message ?? 'Shop đã nhận phản hồi của bạn. Bạn có thể đóng trang này.'}
        </p>
      </CardContent>
    </Card>
  )
}

/** Page frame shared by the confirmation page and its error states. */
export function ConfirmationShell({ shopName, children }: { shopName?: string; children: React.ReactNode }) {
  return (
    <div className="min-h-svh bg-muted/40">
      <main className="mx-auto flex w-full max-w-xl flex-col gap-4 px-4 py-8">
        <header className="flex items-center gap-2">
          <Item className="size-8 justify-center bg-primary p-0 text-primary-foreground" aria-hidden="true">
            <ItemMedia variant="icon" className="size-auto">
              <ShieldCheckIcon className="size-4" />
            </ItemMedia>
          </Item>
          <div className="flex flex-col">
            <span className="text-sm font-semibold">{shopName ?? 'Xác nhận đơn hàng'}</span>
            <span className="text-xs text-muted-foreground">Xác nhận đơn hàng · bảo vệ bởi COD Guard</span>
          </div>
        </header>
        {children}
        <p className="text-center text-xs text-muted-foreground">
          Shop không bao giờ hỏi mật khẩu, mã OTP hay thông tin ngân hàng qua trang này.
        </p>
      </main>
    </div>
  )
}
