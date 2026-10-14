import { createFileRoute } from '@tanstack/react-router'

import { ComingSoon } from '@/components/coming-soon'

// Buyer confirmation page: public, no login, outside the shop layout (E6.1).
export const Route = createFileRoute('/c/$token')({
  component: ConfirmationPage,
})

function ConfirmationPage() {
  return (
    <div className="mx-auto flex min-h-svh max-w-md flex-col justify-center p-4">
      <ComingSoon epic="E6.1" title="Xác nhận đơn hàng" />
    </div>
  )
}
