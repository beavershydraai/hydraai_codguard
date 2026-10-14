/**
 * fetch for the generated API client with the in-browser mock behind it.
 *
 * VITE_API_MOCK:
 * - `all`: every request is answered by the mock (no backend needed).
 * - `fallback` (default): requests go to the backend; a 501 `not_implemented` answer, i.e. an
 *   endpoint that is in the contract but not built yet, is replaced by the mock's answer.
 * - `off`: the backend only.
 */
import { useMockStore } from '@/stores/mock'

export type MockMode = 'all' | 'fallback' | 'off'

export const mockMode: MockMode =
  (['all', 'fallback', 'off'] as const).find((mode) => mode === import.meta.env.VITE_API_MOCK) ?? 'fallback'

async function fromMock(request: Request): Promise<Response | null> {
  // Loaded on first use, so a build that never needs the mock does not download it eagerly.
  const { handle } = await import('./handlers')
  const answer = await handle(request)
  if (!answer) return null
  useMockStore.getState().record(answer.operation)
  return answer.response
}

// Looked up on each call, so tests can stub the global fetch after the client is created.
const globalFetch: typeof fetch = (input, init) => globalThis.fetch(input, init)

export function createMockAwareFetch(realFetch: typeof fetch = globalFetch): typeof fetch {
  return async (input, init) => {
    const request = new Request(input, init)
    if (mockMode === 'all') {
      return (await fromMock(request)) ?? new Response(null, { status: 404 })
    }
    const response = await realFetch(request.clone())
    if (mockMode === 'fallback' && response.status === 501) {
      return (await fromMock(request)) ?? response
    }
    return response
  }
}
