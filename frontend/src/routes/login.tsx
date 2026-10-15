import { createFileRoute, redirect, useRouter } from '@tanstack/react-router'

import { Page } from '@/components/blocks/auth-4/page'
import { safeRedirect } from '@/lib/auth'
import { useAuthStore } from '@/stores/auth'

type LoginSearch = {
  /** Where to go after signing in (set by the shop layout's guard). */
  redirect?: string
}

export const Route = createFileRoute('/login')({
  validateSearch: (search: Record<string, unknown>): LoginSearch => ({
    redirect: typeof search.redirect === 'string' ? search.redirect : undefined,
  }),
  beforeLoad: () => {
    if (useAuthStore.getState().token) throw redirect({ to: '/' })
  },
  component: LoginPage,
})

function LoginPage() {
  const { redirect: target } = Route.useSearch()
  const router = useRouter()

  const safeTarget = safeRedirect(target)

  // `redirect` is a full href (path + search), so push it onto history as is.
  return <Page onSignedIn={() => router.history.push(safeTarget)} />
}
