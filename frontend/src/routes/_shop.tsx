import { createFileRoute, Navigate, Outlet, redirect } from '@tanstack/react-router'

import { AppShell } from '@/components/blocks/app-shell-1/components/app-shell'
import { useAuthStore } from '@/stores/auth'

export const Route = createFileRoute('/_shop')({
  beforeLoad: ({ location }) => {
    if (!useAuthStore.getState().token) {
      throw redirect({ to: '/login', search: { redirect: location.href } })
    }
  },
  staticData: { crumb: 'COD Guard' },
  component: ShopLayout,
})

function ShopLayout() {
  // Signing out, or a 401 from the API, clears the token while the shell is mounted.
  const token = useAuthStore((state) => state.token)
  if (!token) return <Navigate to="/login" />

  return (
    <AppShell>
      <Outlet />
    </AppShell>
  )
}
