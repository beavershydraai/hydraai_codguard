import type { CreateClientConfig } from './gen/client.gen'

import { useAuthStore } from '@/stores/auth'

// Runtime config for the generated client (see openapi-ts.config.ts).
// Empty base URL: requests go to the same origin. `vite dev` proxies /api (see vite.config.ts) and
// Firebase Hosting will rewrite /api to Cloud Run, so the browser never needs CORS.
export const createClientConfig: CreateClientConfig = (config) => ({
  ...config,
  baseUrl: import.meta.env.VITE_API_URL ?? '',
  // Called for operations secured by `firebaseAuth` (bearer).
  auth: () => useAuthStore.getState().token ?? undefined,
})
