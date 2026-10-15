import type { CreateClientConfig } from './gen/client.gen'

import { createMockAwareFetch } from '@/mocks/fetch'
import { useAuthStore } from '@/stores/auth'

// Runtime config for the generated client (see openapi-ts.config.ts).
// Empty base URL: requests go to the same origin. `vite dev` proxies /api (see vite.config.ts) and
// Firebase Hosting will rewrite /api to Cloud Run, so the browser never needs CORS.
export const createClientConfig: CreateClientConfig = (config) => ({
  ...config,
  baseUrl: import.meta.env.VITE_API_URL ?? '',
  // Called for operations secured by `bearerAuth`.
  auth: () => useAuthStore.getState().token ?? undefined,
  // Endpoints the backend has not built yet (501) are answered by the in-browser mock.
  fetch: createMockAwareFetch(),
})
