import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import { toast } from 'sonner'

import { overrideOrder } from '@/api/gen'
import { acceptSuggestionMutation, listOrdersOptions } from '@/api/gen/@tanstack/react-query.gen'
import { REVIEW_DECISIONS } from '@/components/blocks/solution-agents-5/components/review-columns'
import {
  ReviewInbox,
  type SessionDecision,
} from '@/components/blocks/solution-agents-5/components/review-inbox'
import { QueryError } from '@/components/query-error'
import { invalidate, problemMessage } from '@/lib/api'

const QUEUE = { status: ['pending_review' as const], sort: '-updated_at' as const, limit: 200 }

export const Route = createFileRoute('/_shop/review')({
  staticData: { crumb: 'Pending review' },
  // Not awaited: the page renders its skeleton while the data loads.
  loader: ({ context }) => {
    void context.queryClient.prefetchQuery(listOrdersOptions({ query: QUEUE }))
  },
  component: ReviewPage,
})

function ReviewPage() {
  const queryClient = useQueryClient()
  const { data, error, isPending, refetch } = useQuery({
    ...listOrdersOptions({ query: QUEUE }),
    refetchInterval: 30_000,
  })
  const [decisions, setDecisions] = useState<SessionDecision[]>([])
  const accept = useMutation({
    ...acceptSuggestionMutation(),
    onSuccess: (order) => {
      toast.success(`Accepted for ${order.external_id ?? order.id}`, {
        description: 'The buyer is contacted now.',
      })
      void invalidate(queryClient, 'listOrders', 'getOrder')
    },
    onError: (err) => toast.error('Could not accept the suggestion', { description: problemMessage(err) }),
  })

  if (error) return <QueryError error={error} />

  return (
    <ReviewInbox
      orders={data?.items ?? []}
      isLoading={isPending}
      decisions={decisions}
      onRefresh={() => void refetch()}
      onAccept={(order) => accept.mutate({ path: { order_id: order.id } })}
      onDecide={async (orders, action, reason) => {
        const results = await Promise.allSettled(
          orders.map((order) =>
            overrideOrder({ path: { order_id: order.id }, body: { action, reason }, throwOnError: true }),
          ),
        )
        const now = new Date().toISOString()
        setDecisions((current) => [
          ...results.map((result, i) => ({
            at: now,
            orderLabel: orders[i]!.external_id ?? orders[i]!.id,
            action,
            reason,
            ok: result.status === 'fulfilled',
          })),
          ...current,
        ])
        const failed = results.filter((r): r is PromiseRejectedResult => r.status === 'rejected')
        const label = REVIEW_DECISIONS.find((d) => d.action === action)!.label
        if (failed.length === 0)
          toast.success(`${label}: ${orders.length} ${orders.length === 1 ? 'order' : 'orders'}`, {
            description: reason,
          })
        else
          toast.error(`${failed.length}/${orders.length} orders could not be updated`, {
            description: problemMessage(failed[0]!.reason),
          })
        await invalidate(queryClient, 'listOrders', 'getOrder')
      }}
    />
  )
}
