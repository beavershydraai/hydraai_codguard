import { createFileRoute } from '@tanstack/react-router'

import { ComingSoon } from '@/components/coming-soon'
import { PageHeader } from '@/components/page-header'

export const Route = createFileRoute('/_shop/review')({
  component: ReviewPage,
})

function ReviewPage() {
  return (
    <>
      <PageHeader title="Chờ duyệt" description="Đơn cần shop quyết định trước khi gửi." />
      <ComingSoon epic="E7.4" title="Hàng chờ duyệt tay" />
    </>
  )
}
