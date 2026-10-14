import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createRouter, RouterProvider } from '@tanstack/react-router'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { client } from './api/gen/client.gen'
import './index.css'
import { routeTree } from './routeTree.gen'
import { useAuthStore } from './stores/auth'
import { syncThemeWithDocument } from './stores/theme'

syncThemeWithDocument()

// An expired or revoked token signs the user out; the shop layout then shows the login page.
client.interceptors.response.use((response) => {
  if (response.status === 401) useAuthStore.getState().signOut()
  return response
})

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
})

const router = createRouter({
  routeTree,
  context: { queryClient },
  defaultPreload: 'intent',
  // Let TanStack Query decide freshness; the router always calls the loaders.
  defaultPreloadStaleTime: 0,
  scrollRestoration: true,
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
