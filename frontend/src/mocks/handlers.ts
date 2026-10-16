/**
 * Route table of the in-browser mock API. Each handler answers like the backend contract
 * (api/openapi.yaml): JSON bodies on success, problem+json on errors.
 */
import type { DecisionAction, ListOrdersData, OrderStatus, RiskTier } from '@/api/gen'

import { MockError, mockDb } from './db'

type Ctx = { request: Request; params: Record<string, string>; url: URL; body: () => Promise<unknown> }
type Handler = (ctx: Ctx) => unknown | Promise<unknown>
type Route = { method: string; pattern: RegExp; keys: string[]; status: number; handler: Handler }

const routes: Route[] = []

function on(method: string, path: string, handler: Handler, status = 200) {
  const keys: string[] = []
  const pattern = new RegExp(
    '^' + path.replace(/\{(\w+)\}/g, (_, key: string) => (keys.push(key), '([^/]+)')) + '$',
  )
  routes.push({ method, pattern, keys, status, handler })
}

const ME = {
  user_id: 'usr_admin',
  email: 'admin@gmail.com',
  display_name: 'Admin',
  shop_id: 'shop_demo',
}
const me = () => ({ ...ME, role: mockDb.role })

function ownerOnly() {
  if (mockDb.role !== 'owner') {
    throw new MockError(403, 'forbidden', 'Only the shop owner can change costs and policy.')
  }
}

on('POST', '/api/v1/auth/login', async ({ body }) => {
  const { username, password } = (await body()) as { username?: string; password?: string }
  if (username !== ME.email || password !== 'admin12345') {
    throw new MockError(401, 'unauthorized', 'Wrong username or password.')
  }
  return {
    access_token: 'mock-access-token',
    token_type: 'bearer',
    expires_at: new Date(Date.now() + 12 * 3_600_000).toISOString(),
    user: me(),
  }
})
on('GET', '/api/v1/me', me)

on('GET', '/api/v1/shop', () => mockDb.shop)
on('PATCH', '/api/v1/shop', async ({ body }) => {
  ownerOnly()
  return mockDb.updateShop((await body()) as never)
})
on('GET', '/api/v1/shop/policy', () => mockDb.policy)
on('PUT', '/api/v1/shop/policy', async ({ body }) => {
  ownerOnly()
  return mockDb.updatePolicy((await body()) as never, ME.email)
})
on('GET', '/api/v1/shop/policy/versions', () => [...mockDb.policies].reverse())

on('GET', '/api/v1/orders', ({ url }) => {
  const p = url.searchParams
  const query: NonNullable<ListOrdersData['query']> = {
    status: p.getAll('status') as OrderStatus[],
    tier: p.getAll('tier') as RiskTier[],
    branch: p.getAll('branch'),
    q: p.get('q'),
    placed_from: p.get('placed_from'),
    placed_to: p.get('placed_to'),
    sort: (p.get('sort') as NonNullable<ListOrdersData['query']>['sort']) ?? undefined,
    cursor: p.get('cursor'),
    limit: p.has('limit') ? Number(p.get('limit')) : undefined,
  }
  return mockDb.list(query)
})
on('POST', '/api/v1/orders', async ({ body }) => mockDb.create((await body()) as never), 201)
on('POST', '/api/v1/orders/import', async ({ request }) => {
  const form = await request.formData()
  const file = form.get('file')
  if (!(file instanceof Blob)) throw new MockError(400, 'validation_error', 'Missing file.')
  return mockDb.importOrders(await file.text())
})
on('GET', '/api/v1/orders/{order_id}', ({ params }) => mockDb.get(params.order_id!))
on('PATCH', '/api/v1/orders/{order_id}', async ({ params, body }) =>
  mockDb.update(params.order_id!, (await body()) as never, ME.email),
)
on('POST', '/api/v1/orders/{order_id}/override', async ({ params, body }) => {
  const { action, reason } = (await body()) as { action: DecisionAction; reason: string }
  if (!reason || reason.trim().length < 3) {
    throw new MockError(422, 'validation_error', 'A reason of at least 3 characters is required.', {
      errors: [
        {
          loc: ['body', 'reason'],
          msg: 'String should have at least 3 characters',
          type: 'string_too_short',
        },
      ],
    })
  }
  return mockDb.override(params.order_id!, action, reason, ME.email)
})
on('POST', '/api/v1/orders/{order_id}/calls', ({ params }) => mockDb.startCall(params.order_id!), 202)
on('GET', '/api/v1/calls/{call_id}', ({ params }) => mockDb.getCall(params.call_id!))

on('POST', '/api/v1/delivery-outcomes/import', async ({ request }) => {
  const form = await request.formData()
  const file = form.get('file')
  if (!(file instanceof Blob)) throw new MockError(400, 'validation_error', 'Missing file.')
  return mockDb.importDelivery(await file.text())
})

on('GET', '/api/v1/dashboard/summary', ({ url }) => {
  const today = new Date().toISOString().slice(0, 10)
  return mockDb.dashboard(url.searchParams.get('from') ?? today, url.searchParams.get('to') ?? today)
})
on('GET', '/api/v1/dashboard/backtest', () => mockDb.backtest())

on('GET', '/api/v1/public/confirmations/{token}', ({ params }) => mockDb.confirmation(params.token!))
on('POST', '/api/v1/public/confirmations/{token}', async ({ params, body }) =>
  mockDb.respond(params.token!, (await body()) as never),
)

on('POST', '/api/v1/demo/reset', () => mockDb.reset())
on('POST', '/api/v1/demo/spam-simulation', () => mockDb.spamSimulation())

const TITLES: Record<number, string> = {
  400: 'Bad request',
  401: 'Unauthorized',
  403: 'Forbidden',
  404: 'Not found',
  409: 'Conflict',
  410: 'Gone',
  422: 'Validation error',
}

function problem(status: number, code: string, detail: string, extra: Record<string, unknown> = {}) {
  return new Response(
    JSON.stringify({ type: 'about:blank', title: TITLES[status] ?? 'Error', status, code, detail, ...extra }),
    { status, headers: { 'Content-Type': 'application/problem+json' } },
  )
}

/** Answers a request from the mock routes, or returns null when no route matches. */
export async function handle(request: Request): Promise<{ response: Response; operation: string } | null> {
  const url = new URL(request.url, 'http://localhost')
  for (const route of routes) {
    if (route.method !== request.method) continue
    const match = route.pattern.exec(url.pathname)
    if (!match) continue
    const params = Object.fromEntries(route.keys.map((key, i) => [key, decodeURIComponent(match[i + 1]!)]))
    const operation = `${route.method} ${route.pattern.source.replace(/^\^|\$$/g, '').replace(/\(\[\^\/\]\+\)/g, '{id}')}`
    try {
      const result = await route.handler({ request, params, url, body: () => request.clone().json() })
      // A short delay so loading states are visible, as with a real network.
      await new Promise((resolve) => setTimeout(resolve, 150 + Math.random() * 200))
      return {
        operation,
        response: new Response(JSON.stringify(result), {
          status: route.status,
          headers: { 'Content-Type': 'application/json' },
        }),
      }
    } catch (error) {
      if (error instanceof MockError) {
        return { operation, response: problem(error.status, error.code, error.message, error.extra) }
      }
      throw error
    }
  }
  return null
}
