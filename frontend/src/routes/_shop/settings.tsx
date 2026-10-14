import { createFileRoute } from '@tanstack/react-router'

import { ComingSoon } from '@/components/coming-soon'
import { PageHeader } from '@/components/page-header'

export const Route = createFileRoute('/_shop/settings')({
  component: SettingsPage,
})

function SettingsPage() {
  return (
    <>
      <PageHeader title="Cài đặt" description="Chi phí giao thất bại, giờ liên hệ và policy theo tier." />
      <ComingSoon epic="E7.1, E7.6" title="Cài đặt shop" />
    </>
  )
}
