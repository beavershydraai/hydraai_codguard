import { useQuery } from '@tanstack/react-query'
import { createFileRoute, useNavigate } from '@tanstack/react-router'

import {
  getMeOptions,
  getPolicyOptions,
  getShopOptions,
  listPolicyVersionsOptions,
} from '@/api/gen/@tanstack/react-query.gen'
import { type SettingsTab, ShopSettingsView } from '@/components/blocks/settings-3/components/shop-settings'
import { QueryError } from '@/components/query-error'
import { Skeleton } from '@/components/ui/skeleton'

const TABS: SettingsTab[] = ['shop', 'policy', 'history']

export const Route = createFileRoute('/_shop/settings')({
  staticData: { crumb: 'Cài đặt' },
  validateSearch: (search: Record<string, unknown>): { tab?: SettingsTab } => ({
    tab: TABS.includes(search.tab as SettingsTab) ? (search.tab as SettingsTab) : undefined,
  }),
  component: SettingsPage,
})

function SettingsPage() {
  const { tab = 'shop' } = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })
  const me = useQuery(getMeOptions())
  const shop = useQuery(getShopOptions())
  const policy = useQuery(getPolicyOptions())
  const versions = useQuery(listPolicyVersionsOptions())

  const error = shop.error ?? policy.error ?? versions.error
  if (error) return <QueryError error={error} />
  if (!shop.data || !policy.data || !versions.data || !me.data) {
    return (
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-9 w-80" />
        <Skeleton className="h-96 w-full" />
      </div>
    )
  }
  return (
    <ShopSettingsView
      // Remount the forms when saved data changes, so they show what the server stored.
      key={`${shop.data.name}-${policy.data.version}`}
      shop={shop.data}
      policy={policy.data}
      versions={versions.data}
      canEdit={me.data.role === 'owner'}
      tab={tab}
      onTabChange={(next) => navigate({ search: { tab: next === 'shop' ? undefined : next }, replace: true })}
    />
  )
}
