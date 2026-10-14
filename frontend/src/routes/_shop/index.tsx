import { createFileRoute } from '@tanstack/react-router'

import { ComingSoon } from '@/components/coming-soon'
import { PageHeader } from '@/components/page-header'

export const Route = createFileRoute('/_shop/')({
  staticData: { crumb: 'Tổng quan' },
  component: DashboardPage,
})

function DashboardPage() {
  return (
    <>
      <PageHeader title="Tổng quan" description="Hiệu quả sàng lọc đơn COD của shop." />
      <ComingSoon epic="E7.5" title="Dashboard ROI" />
    </>
  )
}
