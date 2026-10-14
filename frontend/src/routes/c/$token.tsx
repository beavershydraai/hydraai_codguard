import { useMutation, useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import { ClockIcon, SearchXIcon } from 'lucide-react'

import { getConfirmationOptions, respondConfirmationMutation } from '@/api/gen/@tanstack/react-query.gen'
import {
  ConfirmationPage,
  ConfirmationShell,
} from '@/components/blocks/receipt-6/components/confirmation-page'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { isProblem, problemMessage } from '@/lib/api'

// Buyer confirmation page: public, no login, outside the shop layout (E6.1).
export const Route = createFileRoute('/c/$token')({
  component: ConfirmationRoute,
})

function ConfirmationRoute() {
  const { token } = Route.useParams()
  const view = useQuery({ ...getConfirmationOptions({ path: { token } }), retry: false })
  const respond = useMutation(respondConfirmationMutation())

  if (view.isPending) {
    return (
      <ConfirmationShell>
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-24 w-full" />
      </ConfirmationShell>
    )
  }
  if (view.error || !view.data) {
    const expired = isProblem(view.error) && (view.error.code === 'link_expired' || view.error.status === 410)
    return (
      <ConfirmationShell>
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-8 text-center">
            {expired ? (
              <ClockIcon className="size-8 text-muted-foreground" aria-hidden="true" />
            ) : (
              <SearchXIcon className="size-8 text-muted-foreground" aria-hidden="true" />
            )}
            <p className="font-medium">{expired ? 'Link đã hết hạn' : 'Không tìm thấy đơn hàng'}</p>
            <p className="max-w-sm text-sm text-muted-foreground">
              {expired
                ? 'Link xác nhận chỉ dùng được trong 48 giờ. Vui lòng liên hệ shop nếu bạn vẫn muốn nhận hàng.'
                : 'Link không đúng hoặc đơn đã bị xóa. Hãy kiểm tra lại tin nhắn từ shop.'}
            </p>
          </CardContent>
        </Card>
      </ConfirmationShell>
    )
  }

  return (
    <ConfirmationPage
      view={view.data}
      pending={respond.isPending}
      error={respond.isError ? problemMessage(respond.error) : null}
      result={respond.data ?? null}
      onRespond={(action, newAddress) =>
        respond.mutate({
          path: { token },
          body: { action, new_address: newAddress ? { raw: newAddress } : null },
        })
      }
    />
  )
}
