import type { QueryClient } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { createRootRouteWithContext, Link, Outlet } from '@tanstack/react-router'
import { TanStackRouterDevtools } from '@tanstack/react-router-devtools'

export type RouterContext = {
  queryClient: QueryClient
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootLayout,
  notFoundComponent: NotFound,
})

function RootLayout() {
  return (
    <>
      <Outlet />
      {import.meta.env.DEV && (
        <>
          <TanStackRouterDevtools position="bottom-right" />
          <ReactQueryDevtools buttonPosition="bottom-left" />
        </>
      )}
    </>
  )
}

function NotFound() {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-2 p-6 text-center">
      <p className="text-lg font-medium">Page not found</p>
      <Link to="/" className="text-sm text-muted-foreground underline underline-offset-4">
        Back to home
      </Link>
    </div>
  )
}
