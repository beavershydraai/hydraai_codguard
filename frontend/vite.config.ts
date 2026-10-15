/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import { tanstackRouter } from '@tanstack/router-plugin/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  // The router plugin must run before the React plugin.
  plugins: [tanstackRouter({ target: 'react', autoCodeSplitting: true }), react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    // Same-origin API calls in development, to the local backend by default. Set
    // API_PROXY_TARGET=http://127.0.0.1:4010 to use the Prism mock (see api/README.md).
    proxy: { '/api': process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8080' },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
