import { defineConfig } from '@hey-api/openapi-ts'

// Generates the typed API client from the contract exported by the backend.
// Run `pnpm generate:api` after api/openapi.yaml changes; CI fails when src/api/gen is stale.
export default defineConfig({
  input: '../api/openapi.yaml',
  output: { path: 'src/api/gen', postProcess: ['prettier'] },
  plugins: [
    { name: '@hey-api/client-fetch', runtimeConfigPath: './src/api/client-config.ts' },
    '@hey-api/typescript',
    '@hey-api/sdk',
    '@tanstack/react-query',
  ],
})
