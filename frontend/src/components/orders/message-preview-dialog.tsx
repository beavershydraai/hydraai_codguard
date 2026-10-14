import { Link } from '@tanstack/react-router'
import { useEffect, useState } from 'react'

import type { ContactAttempt, OrderDetail } from '@/api/gen'
import { Badge } from '@/components/reui/badge'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { formatDateTime, formatVnd } from '@/lib/labels'

/** Simulated Zalo ZNS / SMS the buyer received (E6.2). Always labelled "mock". */
export function MessagePreviewDialog({
  order,
  contact,
  shopName,
  onOpenChange,
}: {
  order: OrderDetail
  contact: ContactAttempt | null
  shopName: string
  onOpenChange: (open: boolean) => void
}) {
  const token = useMockToken(order.id, !!contact)
  const deposit = contact?.channel === 'deposit_request'
  const link = token ? `/c/${token}` : null

  return (
    <Dialog open={!!contact} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            Tin Zalo ZNS / SMS
            <Badge variant="warning-light">mock</Badge>
          </DialogTitle>
          <DialogDescription>Bản xem trước. Bản demo không gửi Zalo ZNS hay SMS thật.</DialogDescription>
        </DialogHeader>
        {contact && (
          <div className="rounded-2xl bg-muted p-3">
            <div className="rounded-xl bg-background p-3 text-sm shadow-xs">
              <p className="mb-1 text-xs font-semibold text-primary">{shopName}</p>
              <p>
                Xin chào {order.buyer_name.split(' ').pop()}, {shopName} nhận được đơn{' '}
                {order.external_id ?? order.id} ({order.items.map((i) => i.name).join(', ')}), thu hộ{' '}
                {formatVnd(order.cod_amount_vnd)}.
              </p>
              <p className="mt-2">
                {deposit
                  ? 'Vui lòng đặt cọc để shop gửi hàng:'
                  : 'Vui lòng xác nhận, sửa địa chỉ hoặc hủy đơn tại:'}{' '}
                {link ? (
                  <Link
                    to="/c/$token"
                    params={{ token: token! }}
                    className="text-primary underline"
                    target="_blank"
                  >
                    codguard.vn{link}
                  </Link>
                ) : (
                  <span className="text-primary underline">codguard.vn/c/…</span>
                )}
              </p>
              {contact.link_expires_at && (
                <p className="mt-2 text-xs text-muted-foreground">
                  Link hết hạn lúc {formatDateTime(contact.link_expires_at)}.
                </p>
              )}
            </div>
            <p className="mt-2 text-center text-[11px] text-muted-foreground">
              {formatDateTime(contact.created_at)}
            </p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

/** The buyer-page token only exists in the mock until the backend serves links (E6.1). */
function useMockToken(orderId: string, enabled: boolean) {
  const [token, setToken] = useState<string | null>(null)
  useEffect(() => {
    if (!enabled) return
    let live = true
    void import('@/mocks/db').then(({ mockDb }) => {
      if (live) setToken(mockDb.orders.get(orderId)?.confirmation_token ?? null)
    })
    return () => {
      live = false
    }
  }, [orderId, enabled])
  return token
}
