import { beforeEach, describe, expect, it } from 'vitest'

import { MockDb, parseCsv } from './db'
import { handle } from './handlers'
import { seedData } from './seed'

describe('seed data', () => {
  const { orders } = seedData(2026, Date.parse('2026-10-15T03:00:00Z'))

  it('is deterministic for a seed and time', () => {
    const again = seedData(2026, Date.parse('2026-10-15T03:00:00Z'))
    expect(again.orders.map((o) => o.id)).toEqual(orders.map((o) => o.id))
    expect(again.orders.map((o) => o.risk_score)).toEqual(orders.map((o) => o.risk_score))
  })

  it('uses only the invalid +84000 test prefix for valid-looking phones', () => {
    for (const o of orders) {
      if (o.current_score?.hard_rules?.includes('invalid_phone')) continue
      expect(o.buyer_phone).toMatch(/^\+84000\d{6}$/)
    }
  })

  it('gives at most 3 reasons, each backed by a signal on the order', () => {
    for (const o of orders) {
      const reasons = o.current_score?.reasons ?? []
      expect(reasons.length).toBeLessThanOrEqual(3)
      const keys = new Set(o.current_score?.top_signals?.map((s) => s.key))
      for (const reason of reasons) for (const key of reason.signal_keys) expect(keys.has(key)).toBe(true)
    }
  })

  it('covers every order state', () => {
    expect(new Set(orders.map((o) => o.status))).toEqual(
      new Set([
        'new',
        'cleared_to_ship',
        'awaiting_confirmation',
        'awaiting_deposit',
        'pending_review',
        'cancelled',
        'shipped',
        'delivered',
        'delivery_failed',
      ]),
    )
  })
})

describe('MockDb', () => {
  let db: MockDb
  beforeEach(() => {
    db = new MockDb()
  })

  it('filters, searches and pages the inbox like the backend', () => {
    const review = db.list({ status: ['pending_review'], limit: 200 })
    expect(review.items.every((o) => o.status === 'pending_review')).toBe(true)

    const first = db.list({ limit: 10 })
    const second = db.list({ limit: 10, cursor: first.next_cursor })
    expect(second.items[0]!.id).not.toBe(first.items[0]!.id)
    expect(() => db.list({ limit: 10, cursor: first.next_cursor, tier: ['high'] })).toThrow()

    const someone = first.items[0]!
    const folded = someone.buyer_name.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/Đ/g, 'D')
    expect(db.list({ q: folded.toLowerCase() }).items.map((o) => o.id)).toContain(someone.id)
  })

  it('records who overrode, when and why', () => {
    const order = db.list({ status: ['pending_review'] }).items[0]!
    const detail = db.override(order.id, 'ship_now', 'Khách quen', 'admin@gmail.com')
    expect(detail.status).toBe('cleared_to_ship')
    expect(detail.decision?.decided_by).toBe('staff')
    expect(detail.timeline?.[0]).toMatchObject({
      type: 'override',
      actor: 'admin@gmail.com',
      reason: 'Khách quen',
    })
  })

  it('blocks a phone after "Tôi không đặt" on the buyer page', () => {
    const order = [...db.orders.values()].find(
      (o) => o.status === 'awaiting_confirmation' && o.confirmation_token,
    )!
    const view = db.confirmation(order.confirmation_token!)
    expect(view.phone_masked).not.toBe(order.buyer_phone)
    expect(view.allowed_actions).toContain('not_ordered')
    db.respond(order.confirmation_token!, { action: 'not_ordered' })
    expect(db.get(order.id).status).toBe('cancelled')
    expect(() => db.respond(order.confirmation_token!, { action: 'confirm' })).toThrow()
  })

  it('imports 1,000 orders without errors (E7.2)', () => {
    const header = 'external_id,channel,buyer_name,buyer_phone,address,item_name,quantity,unit_price_vnd'
    const rows = Array.from(
      { length: 1000 },
      (_, i) => `BULK-${i},website,Khách ${i},+84000${String(i).padStart(6, '0')},"Số ${i}, phường Mẫu, Hà Nội",Áo,1,189000`,
    )
    const result = db.importOrders([header, ...rows].join('\n'))
    expect(result).toMatchObject({ received: 1000, imported: 1000, duplicates: 0, rejected: [] })
    expect(db.list({ q: 'BULK-999' }).items).toHaveLength(1)
  })

  it('imports orders from CSV and reports bad rows', () => {
    const csv =
      'external_id,channel,buyer_name,buyer_phone,address,item_name,quantity,unit_price_vnd\n' +
      'IMP-1,facebook,Khách A,0000000001,"Số 1, phường Mẫu, Hà Nội",Áo,1,100000\n' +
      'IMP-2,zalo,Khách B,123,"Số 2, phường Mẫu",Áo,1,100000\n'
    const result = db.importOrders(csv)
    expect(result).toMatchObject({ received: 2, imported: 1, duplicates: 0 })
    expect(result.rejected?.[0]).toMatchObject({ row: 2, field: 'buyer_phone' })
  })
})

describe('mock routes', () => {
  it('answers the contract with JSON and problem+json', async () => {
    const ok = await handle(new Request('http://localhost/api/v1/orders?status=pending_review&limit=5'))
    expect(ok?.response.status).toBe(200)
    expect((await ok!.response.json()).items.length).toBeGreaterThan(0)

    const missing = await handle(new Request('http://localhost/api/v1/orders/ord_nope'))
    expect(missing?.response.status).toBe(404)
    expect(missing?.response.headers.get('content-type')).toBe('application/problem+json')

    expect(await handle(new Request('http://localhost/api/v1/unknown'))).toBeNull()
  })
})

it('parses quoted CSV cells', () => {
  expect(parseCsv('a,"b, c","say ""hi"""\r\n1,2,3')).toEqual([
    ['a', 'b, c', 'say "hi"'],
    ['1', '2', '3'],
  ])
})
