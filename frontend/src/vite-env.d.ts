/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API origin. Leave unset to call the same origin (dev proxy or Firebase Hosting rewrite). */
  readonly VITE_API_URL?: string
  /** `all` (mock everything), `fallback` (mock only 501 answers, default) or `off`. */
  readonly VITE_API_MOCK?: 'all' | 'fallback' | 'off'
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
