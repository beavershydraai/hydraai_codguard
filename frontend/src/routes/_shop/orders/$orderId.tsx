import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import { toast } from 'sonner'

import type { Call, ContactAttempt } from '@/api/gen'
import {
  acceptSuggestionMutation,
  getOrderOptions,
  getShopOptions,
  startCallMutation,
} from '@/api/gen/@tanstack/react-query.gen'
import { OrderDetailView } from '@/components/blocks/receipt-2/components/order-detail'
import { CallSimulator } from '@/components/orders/call-simulator'
import { EditOrderSheet } from '@/components/orders/edit-order-sheet'
import { MessagePreviewDialog } from '@/components/orders/message-preview-dialog'
import { OverrideDialog } from '@/components/orders/override-dialog'
import { QueryError } from '@/components/query-error'
import { Skeleton } from '@/components/ui/skeleton'
import { invalidate, problemMessage } from '@/lib/api'

export const Route = createFileRoute('/_shop/orders/$orderId')({
  staticData: { crumb: 'Order details' },
  // Not awaited: the page renders its skeleton while the data loads.
  loader: ({ context, params }) => {
    void context.queryClient.prefetchQuery(getOrderOptions({ path: { order_id: params.orderId } }))
  },
  component: OrderDetailPage,
})

// A call in one of these states still changes the order: its progress and result land in the
// contact history, the timeline and the status, so the page polls until the call ends.
const ACTIVE_CALL = new Set<Call['status']>(['queued', 'dialing', 'in_progress'])

function OrderDetailPage() {
  const { orderId } = Route.useParams()
  const queryClient = useQueryClient()
  const orderQuery = useQuery({
    ...getOrderOptions({ path: { order_id: orderId } }),
    refetchInterval: (query) =>
      query.state.data?.calls?.some((c) => ACTIVE_CALL.has(c.status)) ? 3_000 : false,
  })
  const { data: order, error, isPending } = orderQuery
  const { data: shop } = useQuery(getShopOptions())
  const [panel, setPanel] = useState<'edit' | 'override' | null>(null)
  const [call, setCall] = useState<Call | null>(null)
  const [message, setMessage] = useState<ContactAttempt | null>(null)
  const startCall = useMutation({
    ...startCallMutation(),
    onSuccess: (started) => {
      setCall(started)
      void invalidate(queryClient, 'getOrder', 'listOrders')
    },
    onError: (err) => toast.error('Could not start the call', { description: problemMessage(err) }),
  })

  const accept = useMutation({
    ...acceptSuggestionMutation(),
    onSuccess: (updated) => {
      queryClient.setQueryData(getOrderOptions({ path: { order_id: orderId } }).queryKey, updated)
      void invalidate(queryClient, 'listOrders')
      toast.success('Suggestion accepted', { description: 'The buyer is contacted now.' })
    },
    onError: (err) => toast.error('Could not accept the suggestion', { description: problemMessage(err) }),
  })

  if (error) return <QueryError error={error} />
  if (isPending || !order) return <DetailSkeleton />

  const shopName = shop?.name ?? 'shop'
  const confirmed = order.timeline?.some((e) => e.type === 'buyer_responded')
  const callDisabledReason =
    (order.allowed_overrides?.length ?? 0) === 0
      ? 'The order has shipped or is closed.'
      : order.current_score?.hard_rules?.includes('invalid_phone')
        ? 'Invalid phone number.'
        : confirmed
          ? 'The order is confirmed, so the buyer is not contacted again.'
          : (order.calls?.length ?? 0) >= 2
            ? 'Both call attempts have been used.'
            : null

  return (
    <>
      <OrderDetailView
        order={order}
        actions={{
          onCall: () => startCall.mutate({ path: { order_id: order.id } }),
          callDisabledReason: startCall.isPending ? 'Calling…' : callDisabledReason,
          onEdit: () => setPanel('edit'),
          onOverride: () => setPanel('override'),
          onPreviewMessage: setMessage,
          onAcceptSuggestion: () => accept.mutate({ path: { order_id: order.id } }),
          acceptingSuggestion: accept.isPending,
        }}
      />
      <EditOrderSheet
        order={order}
        open={panel === 'edit'}
        onOpenChange={(open) => setPanel(open ? 'edit' : null)}
      />
      <OverrideDialog
        order={order}
        open={panel === 'override'}
        onOpenChange={(open) => setPanel(open ? 'override' : null)}
      />
      <CallSimulator
        order={order}
        call={call}
        shopName={shopName}
        onOpenChange={(open) => !open && setCall(null)}
      />
      <MessagePreviewDialog
        order={order}
        contact={message}
        shopName={shopName}
        onOpenChange={(open) => !open && setMessage(null)}
      />
    </>
  )
}

function DetailSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6" aria-busy="true">
      <Skeleton className="h-8 w-40" />
      <Skeleton className="h-28 w-full" />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[20rem_1fr]">
        <Skeleton className="h-96" />
        <div className="flex flex-col gap-6">
          <Skeleton className="h-64" />
          <Skeleton className="h-40" />
        </div>
      </div>
    </div>
  )
}
