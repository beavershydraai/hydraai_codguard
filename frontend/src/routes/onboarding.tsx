import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, redirect, useNavigate } from '@tanstack/react-router'
import { ShieldCheckIcon } from 'lucide-react'
import { toast } from 'sonner'

import { getPolicyOptions, getShopOptions, updateShopMutation } from '@/api/gen/@tanstack/react-query.gen'
import { failedDeliveryCost, money } from '@/components/blocks/wizard-1/components/data'
import { OnboardingWizard } from '@/components/blocks/wizard-1/components/onboarding-wizard'
import { QueryError } from '@/components/query-error'
import { Button } from '@/components/ui/button'
import { Item, ItemMedia } from '@/components/ui/item'
import { Skeleton } from '@/components/ui/skeleton'
import { invalidate, problemMessage } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { useOnboardingStore } from '@/stores/onboarding'

export const Route = createFileRoute('/onboarding')({
  beforeLoad: ({ location }) => {
    if (!useAuthStore.getState().token) throw redirect({ to: '/login', search: { redirect: location.href } })
  },
  component: OnboardingPage,
})

function OnboardingPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const markDone = useOnboardingStore((s) => s.markDone)
  const shop = useQuery(getShopOptions())
  const policy = useQuery(getPolicyOptions())
  const save = useMutation({
    ...updateShopMutation(),
    onSuccess: (saved) => {
      markDone(saved.id)
      void invalidate(queryClient, 'getShop')
      toast.success('Shop đã sẵn sàng', { description: 'Đơn mới sẽ được chấm điểm ngay khi vào.' })
      void navigate({ to: '/' })
    },
    onError: (error) => toast.error('Không lưu được', { description: problemMessage(error) }),
  })

  const error = shop.error ?? policy.error
  return (
    <div className="flex min-h-svh flex-col items-center gap-6 bg-muted/40 px-4 py-10">
      <div className="flex flex-col items-center gap-3 text-center">
        <Item className="size-10 justify-center bg-primary p-0 text-primary-foreground" aria-hidden="true">
          <ItemMedia variant="icon" className="size-auto">
            <ShieldCheckIcon className="size-5" />
          </ItemMedia>
        </Item>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Thiết lập shop</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            3 bước, khoảng 1 phút. Mọi giá trị đã có sẵn mặc định.
          </p>
        </div>
      </div>
      {error ? (
        <QueryError error={error} />
      ) : !shop.data || !policy.data ? (
        <Skeleton className="h-96 w-full max-w-xl" />
      ) : (
        <OnboardingWizard
          shop={shop.data}
          policy={policy.data}
          submitting={save.isPending}
          onComplete={(values) =>
            save.mutate({
              body: {
                name: values.name.trim(),
                settings: {
                  failed_delivery_cost_vnd: failedDeliveryCost(values),
                  ai_call_cost_vnd: money(values.callCost),
                  contact_hours: { start: values.start, end: values.end },
                },
              },
            })
          }
        />
      )}
      {shop.data && (
        <Button
          variant="link"
          className="text-muted-foreground"
          onClick={() => {
            markDone(shop.data.id)
            void navigate({ to: '/' })
          }}
        >
          Bỏ qua, dùng giá trị mặc định
        </Button>
      )}
    </div>
  )
}
