/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API origin. Leave unset to call the same origin (dev proxy or Firebase Hosting rewrite). */
  readonly VITE_API_URL?: string
  /** Bearer token for local development against the mock server. */
  readonly VITE_DEV_AUTH_TOKEN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
