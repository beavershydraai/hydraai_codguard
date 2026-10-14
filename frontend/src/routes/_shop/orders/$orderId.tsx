import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { ArrowLeft } from 'lucide-react'

import { getOrderOptions } from '@/api/gen/@tanstack/react-query.gen'
import { ComingSoon } from '@/components/coming-soon'
import { PageHeader } from '@/components/page-header'
import { QueryError } from '@/components/query-error'

export const Route = createFileRoute('/_shop/orders/$orderId')({
  loader: ({ context, params }) =>
    context.queryClient.prefetchQuery(getOrderOptions({ path: { order_id: params.orderId } })),
  component: OrderDetailPage,
})

function OrderDetailPage() {
  const { orderId } = Route.useParams()
  const { error } = useQuery(getOrderOptions({ path: { order_id: orderId } }))

  return (
    <>
      <Link
        to="/orders"
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" /> Đơn hàng
      </Link>
      <PageHeader title={`Đơn ${orderId}`} />
      {error ? <QueryError error={error} /> : <ComingSoon epic="E7.3" title="Chi tiết đơn" />}
    </>
  )
}
