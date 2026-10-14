/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API origin. Leave unset to call the same origin (dev proxy or Firebase Hosting rewrite). */
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
