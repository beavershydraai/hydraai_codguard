import { afterEach, describe, expect, it, vi } from 'vitest'

import { client } from '@/api/gen/client.gen'
import { useAuthStore } from '@/stores/auth'

import { safeRedirect, signIn, SignInError } from './auth'

// Node's Request needs an absolute URL; the app itself calls the same origin.
client.setConfig({ baseUrl: 'http://localhost' })

function respond(status: number, body: unknown) {
  const fetch = vi.fn(
    async (_request: Request) =>
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': status < 400 ? 'application/json' : 'application/problem+json' },
      }),
  )
  vi.stubGlobal('fetch', fetch)
  return fetch
}

afterEach(() => {
  vi.unstubAllGlobals()
  useAuthStore.getState().signOut()
})

describe('signIn', () => {
  it('posts the email as username and stores the token', async () => {
    const fetch = respond(200, {
      access_token: 'token-1',
      token_type: 'bearer',
      expires_at: '2026-10-15T08:00:00+07:00',
      user: { user_id: 'usr_admin', email: 'admin@gmail.com', role: 'owner', shop_id: 'shop_demo' },
    })
    await signIn({ email: 'admin@gmail.com', password: 'admin12345' })
    expect(useAuthStore.getState().token).toBe('token-1')
    const request = fetch.mock.calls[0]![0]
    expect(new URL(request.url).pathname).toBe('/api/v1/auth/login')
    expect(await request.json()).toEqual({ username: 'admin@gmail.com', password: 'admin12345' })
  })

  it('reports wrong credentials in English and stores nothing', async () => {
    respond(401, { type: 'about:blank', title: 'Unauthorized', status: 401, code: 'unauthorized' })
    await expect(signIn({ email: 'admin@gmail.com', password: 'nope' })).rejects.toThrow(
      new SignInError('Wrong email or password.'),
    )
    expect(useAuthStore.getState().token).toBeNull()
  })
})

describe('safeRedirect', () => {
  it('keeps paths inside the app, with their search', () => {
    expect(safeRedirect('/orders?tier=high')).toBe('/orders?tier=high')
  })

  it.each([undefined, '', 'https://example.com', '//example.com', '/\\example.com', 'orders'])(
    'falls back to the dashboard for %j',
    (target) => {
      expect(safeRedirect(target)).toBe('/')
    },
  )
})
