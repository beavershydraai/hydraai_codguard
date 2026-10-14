/**
 * Stateful in-memory stand-in for the backend, used by the mock API (src/mocks/handlers.ts).
 * Rules mirror the backend where it exists (inbox filtering and paging) and the domain rules in
 * AGENTS.md where it does not yet (overrides, buyer page, calls, dashboard).
 */
import type {
  BacktestResult,
  BuyerAction,
  BuyerOrderView,
  BuyerResponse,
  BuyerResponseResult,
  Call,
  CallOutcome,
  DashboardSummary,
  DecisionAction,
  DeliveryImportResult,
  ImportResult,
  ImportRowError,
  ListOrdersData,
  OrderCreate,
  OrderDetail,
  OrderEvent,
  OrderPage,
  OrderStatus,
  OrderSummary,
  OrderUpdate,
  Policy,
  PolicyUpdate,
  Shop,
  ShopUpdate,
  SpamSimulationResult,
} from '@/api/gen'

import {
  ALL_ACTIONS,
  CALL_OUTCOME_VI,
  decisionMessage,
  FAILED_DELIVERY_COST,
  maskPhone,
  type MockOrder,
  rng,
  seedData,
  tierFor,
} from './seed'

export class MockError extends Error {
  readonly status: number
  readonly code: string
  readonly extra: Record<string, unknown>

  constructor(status: number, code: string, message: string, extra: Record<string, unknown> = {}) {
    super(message)
    this.status = status
    this.code = code
    this.extra = extra
  }
}

const PRE_SHIP: OrderStatus[] = [
  'new',
  'cleared_to_ship',
  'awaiting_confirmation',
  'awaiting_deposit',
  'pending_review',
]

const nowIso = () => new Date().toISOString()

function fold(text: string): string {
  return text.toLowerCase().replace(/đ/g, 'd').normalize('NFD').replace(/[̀-ͯ]/g, '')
}

function phoneForms(phone: string): string[] {
  const digits = phone.replace(/\D/g, '')
  return digits.startsWith('84') ? [digits, `0${digits.slice(2)}`] : [digits]
}

export function matchesSearch(order: OrderSummary, q: string): boolean {
  const needle = fold(q.trim())
  if (!needle) return true
  if (fold([order.id, order.external_id ?? '', order.buyer_name].join(' ')).includes(needle)) return true
  const digits = q.replace(/\D/g, '')
  return digits.length >= 3 && phoneForms(order.buyer_phone).some((form) => form.includes(digits))
}

export function summary(order: OrderDetail): OrderSummary {
  return {
    id: order.id,
    external_id: order.external_id,
    channel: order.channel,
    buyer_name: order.buyer_name,
    buyer_phone: order.buyer_phone,
    is_gift: order.is_gift,
    total_vnd: order.total_vnd,
    cod_amount_vnd: order.cod_amount_vnd,
    status: order.status,
    tier: order.tier,
    risk_score: order.risk_score,
    current_action: order.current_action,
    placed_at: order.placed_at,
    updated_at: order.updated_at,
  }
}

function publicDetail(order: MockOrder): OrderDetail {
  const { confirmation_token: _token, ...detail } = order
  return structuredClone(detail)
}

type ListQuery = NonNullable<ListOrdersData['query']>

export class MockDb {
  orders = new Map<string, MockOrder>()
  calls = new Map<string, Call>()
  shop!: Shop
  policies: Policy[] = []
  blockedPhones = new Set<string>()
  seed = 2026

  constructor() {
    this.reset()
  }

  reset(seed = this.seed): { seed: number; orders: number } {
    const data = seedData(seed)
    this.seed = seed
    this.orders = new Map(data.orders.map((o) => [o.id, o]))
    this.calls = new Map(data.calls.map((c) => [c.id, c]))
    this.shop = data.shop
    this.policies = data.policies
    this.blockedPhones = new Set()
    return { seed, orders: this.orders.size }
  }

  // ── Shop and policy ──

  updateShop(update: ShopUpdate): Shop {
    this.shop = {
      ...this.shop,
      name: update.name ?? this.shop.name,
      settings: {
        ...this.shop.settings,
        ...Object.fromEntries(
          Object.entries(update.settings ?? {}).filter(([, value]) => value !== null && value !== undefined),
        ),
      },
    }
    return this.shop
  }

  get policy(): Policy {
    return this.policies[this.policies.length - 1]!
  }

  updatePolicy(update: PolicyUpdate, by: string): Policy {
    const next: Policy = {
      version: this.policy.version + 1,
      effective_from: nowIso(),
      updated_by: by,
      tiers: update.tiers,
    }
    this.policies.push(next)
    return next
  }

  // ── Orders ──

  list(query: ListQuery): OrderPage {
    const statuses = query.status ?? []
    const tiers = query.tier ?? []
    const from = query.placed_from ? Date.parse(query.placed_from) : null
    const to = query.placed_to ? Date.parse(query.placed_to) : null
    const sort = query.sort ?? '-placed_at'
    const limit = query.limit ?? 50
    const fingerprint = JSON.stringify([statuses, tiers, query.q, from, to, sort])

    let offset = 0
    if (query.cursor) {
      const [o, f] = atob(query.cursor).split('|')
      if (f !== fingerprint || Number.isNaN(Number(o))) {
        throw new MockError(422, 'validation_error', 'The cursor belongs to a different query.')
      }
      offset = Number(o)
    }

    const rows = [...this.orders.values()]
      .map(summary)
      .filter(
        (o) =>
          (!statuses.length || statuses.includes(o.status)) &&
          (!tiers.length || (o.tier != null && tiers.includes(o.tier))) &&
          (from == null || Date.parse(o.placed_at) >= from) &&
          (to == null || Date.parse(o.placed_at) <= to) &&
          (!query.q || matchesSearch(o, query.q)),
      )
    const key = (o: OrderSummary): [number, string] => {
      switch (sort) {
        case '-updated_at':
          return [Date.parse(o.updated_at), o.id]
        case '-cod_amount_vnd':
          return [o.cod_amount_vnd, o.id]
        case '-risk_score':
          return [o.risk_score == null ? -1 : o.risk_score, o.id]
        default:
          return [Date.parse(o.placed_at), o.id]
      }
    }
    rows.sort((a, b) => {
      const [ka, ia] = key(a)
      const [kb, ib] = key(b)
      return ka - kb || ia.localeCompare(ib)
    })
    if (sort.startsWith('-')) rows.reverse()

    const page = rows.slice(offset, offset + limit)
    const more = offset + limit < rows.length
    return {
      items: page,
      total: rows.length,
      next_cursor: more ? btoa(`${offset + limit}|${fingerprint}`) : null,
    }
  }

  private order(orderId: string): MockOrder {
    const order = this.orders.get(orderId)
    if (!order) throw new MockError(404, 'not_found', `Order ${orderId} not found.`)
    return order
  }

  get(orderId: string): OrderDetail {
    return publicDetail(this.order(orderId))
  }

  private event(order: MockOrder, type: OrderEvent['type'], actor: string, message: string, reason?: string) {
    const at = nowIso()
    order.timeline = [
      { at, type, actor, message_vi: message, reason: reason ?? null },
      ...(order.timeline ?? []),
    ]
    order.updated_at = at
  }

  private setStatus(order: MockOrder, status: OrderStatus) {
    order.status = status
    order.allowed_overrides = PRE_SHIP.includes(status)
      ? ALL_ACTIONS.filter((a) => a !== order.current_action)
      : []
  }

  /** Scores an order from its content, like the engine would, and applies the tier policy. */
  private score(order: MockOrder, actor = 'engine') {
    const r = rng((Date.parse(order.placed_at) % 100_000) + order.cod_amount_vnd)
    const prepaidAll = order.cod_amount_vnd === 0
    const invalidPhone = !/^\+84\d{9,10}$/.test(order.buyer_phone)
    const blocked = this.blockedPhones.has(order.buyer_phone)
    const probability = prepaidAll
      ? 0
      : blocked
        ? 0.9
        : Math.min(0.85, 0.02 + r.next() * 0.45 + (order.cod_amount_vnd > 800_000 ? 0.08 : 0))
    const tier = prepaidAll ? null : tierFor(probability)
    const scoredAt = nowIso()
    const previous = order.current_score
    order.current_score = {
      id: `scr_${order.id}_${(order.score_history?.length ?? 0) + 1}`,
      scored_at: scoredAt,
      status: prepaidAll ? 'skipped' : 'scored',
      skipped_reason: prepaidAll ? 'prepaid_skip' : null,
      probability: prepaidAll ? null : Number(probability.toFixed(3)),
      risk_score: prepaidAll ? null : Math.round(probability * 100),
      tier,
      expected_loss_vnd: prepaidAll
        ? null
        : Math.round(probability * this.shop.settings.failed_delivery_cost_vnd!),
      failed_delivery_cost_vnd: this.shop.settings.failed_delivery_cost_vnd ?? FAILED_DELIVERY_COST,
      hard_rules: prepaidAll ? ['prepaid_skip'] : invalidPhone ? ['invalid_phone'] : [],
      top_signals: previous?.top_signals ?? [],
      reasons: previous?.reasons ?? [],
      model_version: 'cod-guard-gbm-2026.10',
    }
    order.score_history = [
      order.current_score,
      ...(order.score_history ?? []).filter((s) => s.id !== order.current_score!.id),
    ]
    order.tier = tier
    order.risk_score = order.current_score.risk_score
    this.event(
      order,
      'scored',
      actor,
      prepaidAll ? 'Đơn đã trả trước: bỏ qua chấm điểm.' : `Chấm lại: ${order.risk_score}/100.`,
    )

    const confirmed = order.timeline?.some(
      (e) =>
        e.type === 'buyer_responded' || (e.type === 'call_completed' && /Xác nhận|Đã sửa/.test(e.message_vi)),
    )
    const policyAction = invalidPhone
      ? 'hold_for_review'
      : tier
        ? this.policy.tiers.find((t) => t.tier === tier)!.action
        : 'ship_now'
    // A confirmed order is never contacted again.
    const action: DecisionAction = confirmed && policyAction !== 'hold_for_review' ? 'ship_now' : policyAction
    order.decision = {
      decided_at: nowIso(),
      action,
      policy_version: this.policy.version,
      expected_loss_vnd: order.current_score.expected_loss_vnd,
      contact_cost_vnd: null,
      block_reasons: confirmed && policyAction !== action ? ['already_confirmed'] : [],
      decided_by: 'engine',
    }
    order.current_action = action
    this.event(order, 'decided', 'engine', decisionMessage(action))
    this.setStatus(order, statusFor(action))
  }

  create(body: OrderCreate): OrderSummary {
    const duplicate =
      body.external_id && [...this.orders.values()].find((o) => o.external_id === body.external_id)
    if (duplicate) {
      throw new MockError(409, 'conflict', `An order with external_id ${body.external_id} already exists.`)
    }
    const id = `ord_mock_${crypto.randomUUID().slice(0, 8)}`
    const total =
      body.items.reduce((sum, item) => sum + item.quantity * item.unit_price_vnd, 0) -
      (body.discount_vnd ?? 0) +
      (body.shipping_fee_vnd ?? 0)
    const prepaid = body.prepaid_vnd ?? 0
    const order: MockOrder = {
      id,
      external_id: body.external_id ?? null,
      channel: body.channel,
      buyer_name: body.buyer_name,
      buyer_phone: toE164(body.buyer_phone) ?? body.buyer_phone,
      is_gift: body.is_gift ?? false,
      recipient_name: body.recipient_name ?? null,
      recipient_phone: body.recipient_phone ?? null,
      total_vnd: total,
      cod_amount_vnd: Math.max(total - prepaid, 0),
      status: 'new',
      tier: null,
      risk_score: null,
      current_action: null,
      placed_at: body.placed_at,
      updated_at: nowIso(),
      address: body.address,
      items: body.items,
      shipping_fee_vnd: body.shipping_fee_vnd ?? 0,
      discount_vnd: body.discount_vnd ?? 0,
      prepaid_vnd: prepaid,
      note: body.note ?? null,
      current_score: null,
      score_history: [],
      decision: null,
      contacts: [],
      calls: [],
      timeline: [
        { at: nowIso(), type: 'created', actor: 'admin@gmail.com', message_vi: 'Shop tạo đơn thủ công.' },
      ],
      allowed_overrides: [],
    }
    this.orders.set(id, order)
    this.score(order)
    return summary(order)
  }

  update(orderId: string, body: OrderUpdate, actor: string): OrderDetail {
    const order = this.order(orderId)
    if (!PRE_SHIP.includes(order.status)) {
      throw new MockError(409, 'order_not_editable', 'The order has shipped and can no longer be edited.')
    }
    if (body.buyer_name) order.buyer_name = body.buyer_name
    if (body.buyer_phone) order.buyer_phone = toE164(body.buyer_phone) ?? body.buyer_phone
    if (body.recipient_name !== undefined) order.recipient_name = body.recipient_name
    if (body.address) order.address = body.address
    if (body.items) order.items = body.items
    if (body.note !== undefined) order.note = body.note
    if (body.prepaid_vnd != null) order.prepaid_vnd = body.prepaid_vnd
    order.total_vnd =
      order.items.reduce((s, i) => s + i.quantity * i.unit_price_vnd, 0) -
      order.discount_vnd +
      order.shipping_fee_vnd
    order.cod_amount_vnd = Math.max(order.total_vnd - order.prepaid_vnd, 0)
    this.event(order, 'edited', actor, 'Shop sửa đơn trước khi gửi: chấm lại điểm.')
    this.score(order)
    return publicDetail(order)
  }

  override(orderId: string, action: DecisionAction, reason: string, actor: string): OrderDetail {
    const order = this.order(orderId)
    if (!order.allowed_overrides?.includes(action)) {
      throw new MockError(409, 'conflict', 'This action is not allowed for the order in its current state.')
    }
    order.decision = {
      ...(order.decision ?? { policy_version: this.policy.version }),
      decided_at: nowIso(),
      action,
      decided_by: 'staff',
      next_action: null,
      next_action_at: null,
    }
    order.current_action = action
    this.event(order, 'override', actor, `Nhân viên chọn: ${ACTION_VI[action]}.`, reason)
    this.setStatus(order, statusFor(action))
    if (action === 'cancel') this.event(order, 'status_changed', actor, 'Đơn bị hủy bởi shop.')
    return publicDetail(order)
  }

  importOrders(csv: string): ImportResult {
    const rows = parseCsv(csv)
    const header = rows.shift()?.map((h) => h.trim().toLowerCase()) ?? []
    const col = (name: string) => header.indexOf(name)
    const required = ['buyer_name', 'buyer_phone', 'address', 'item_name', 'quantity', 'unit_price_vnd']
    const missing = required.filter((name) => col(name) < 0)
    if (missing.length) {
      throw new MockError(400, 'validation_error', `CSV header is missing: ${missing.join(', ')}.`)
    }
    let imported = 0
    let duplicates = 0
    const rejected: ImportRowError[] = []
    rows.forEach((row, index) => {
      if (row.every((cell) => !cell.trim())) return
      const get = (name: string) => (col(name) >= 0 ? (row[col(name)]?.trim() ?? '') : '')
      const quantity = Number(get('quantity'))
      const price = Number(get('unit_price_vnd'))
      const phone = toE164(get('buyer_phone'))
      if (!get('buyer_name'))
        return rejected.push({ row: index + 1, field: 'buyer_name', message: 'Thiếu tên người mua.' })
      if (!phone)
        return rejected.push({ row: index + 1, field: 'buyer_phone', message: 'Số điện thoại không hợp lệ.' })
      if (!Number.isInteger(quantity) || quantity < 1)
        return rejected.push({
          row: index + 1,
          field: 'quantity',
          message: 'Số lượng phải là số nguyên dương.',
        })
      if (!Number.isFinite(price) || price < 0)
        return rejected.push({ row: index + 1, field: 'unit_price_vnd', message: 'Đơn giá không hợp lệ.' })
      const channel =
        (['facebook', 'tiktok', 'zalo', 'website', 'other'] as const).find((c) => c === get('channel')) ??
        'other'
      try {
        this.create({
          external_id: get('external_id') || null,
          channel,
          buyer_name: get('buyer_name'),
          buyer_phone: phone,
          address: { raw: get('address') },
          items: [{ name: get('item_name'), quantity, unit_price_vnd: price }],
          shipping_fee_vnd: Number(get('shipping_fee_vnd')) || 0,
          prepaid_vnd: Number(get('prepaid_vnd')) || 0,
          placed_at: get('placed_at') || nowIso(),
        })
        imported++
      } catch (error) {
        if (error instanceof MockError && error.status === 409) duplicates++
        else rejected.push({ row: index + 1, message: String(error) })
      }
    })
    return { received: imported + duplicates + rejected.length, imported, duplicates, rejected }
  }

  // ── Calls ──

  startCall(orderId: string): Call {
    const order = this.order(orderId)
    if (this.blockedPhones.has(order.buyer_phone)) {
      throw new MockError(409, 'contact_blocked', 'This phone asked not to be contacted.', {
        block_reasons: ['phone_blocked'],
      })
    }
    if (!PRE_SHIP.includes(order.status) || order.timeline?.some((e) => e.type === 'buyer_responded')) {
      throw new MockError(409, 'contact_blocked', 'A confirmed or shipped order is never contacted again.', {
        block_reasons: ['already_confirmed'],
      })
    }
    const attempt = (order.calls?.length ?? 0) + 1
    if (attempt > 2) {
      throw new MockError(409, 'contact_blocked', 'Both call attempts have been used.', {
        block_reasons: ['attempts_exhausted'],
      })
    }
    const call: Call = {
      id: `call_${order.id}_${attempt}`,
      order_ids: [order.id],
      phone_masked: maskPhone(order.buyer_phone),
      status: 'queued',
      attempt,
      queued_at: nowIso(),
      changes: [],
      summary_vi: null,
    }
    this.calls.set(call.id, call)
    order.calls = [...(order.calls ?? []), call]
    order.contacts = [
      ...(order.contacts ?? []),
      {
        id: `ct_${order.id}_${(order.contacts?.length ?? 0) + 1}`,
        channel: 'ai_call',
        created_at: call.queued_at,
        call_id: call.id,
      },
    ]
    this.setStatus(order, 'awaiting_confirmation')
    this.event(order, 'contact_started', 'admin@gmail.com', `Shop yêu cầu AI gọi xác nhận (lần ${attempt}).`)
    return structuredClone(call)
  }

  getCall(callId: string): Call {
    const call = this.calls.get(callId)
    if (!call) throw new MockError(404, 'not_found', `Call ${callId} not found.`)
    return structuredClone(call)
  }

  /** Simulated phone (E5.2 UI): moves a call along and records its single outcome. */
  progressCall(callId: string, outcome?: CallOutcome, summaryVi?: string): Call {
    const call = this.calls.get(callId)
    if (!call) throw new MockError(404, 'not_found', `Call ${callId} not found.`)
    const now = nowIso()
    if (!outcome) {
      call.status = call.status === 'queued' ? 'dialing' : 'in_progress'
      call.started_at ??= now
    } else {
      call.status = 'completed'
      call.started_at ??= now
      call.ended_at = now
      call.duration_seconds = Math.round((Date.parse(now) - Date.parse(call.started_at)) / 1000)
      call.outcome = outcome
      call.summary_vi = summaryVi ?? null
      for (const orderId of call.order_ids) {
        const order = this.orders.get(orderId)
        if (!order) continue
        order.calls = order.calls?.map((c) => (c.id === call.id ? structuredClone(call) : c))
        order.contacts = order.contacts?.map((c) =>
          c.call_id === call.id
            ? { ...c, responded_at: outcome === 'no_answer' ? null : now, result: outcome }
            : c,
        )
        this.event(order, 'call_completed', 'ai_call', `Kết quả cuộc gọi: ${CALL_OUTCOME_VI[outcome]}.`)
        if (outcome === 'confirmed' || outcome === 'edited') this.setStatus(order, 'cleared_to_ship')
        if (outcome === 'cancelled') this.setStatus(order, 'cancelled')
        if (outcome === 'not_ordered') {
          this.blockedPhones.add(order.buyer_phone)
          this.setStatus(order, 'cancelled')
        }
        if (outcome === 'no_answer' && call.attempt >= 2) this.setStatus(order, 'pending_review')
      }
    }
    return structuredClone(call)
  }

  // ── Buyer confirmation page ──

  private byToken(token: string): MockOrder {
    const order = [...this.orders.values()].find((o) => o.confirmation_token === token)
    if (!order) throw new MockError(404, 'not_found', 'This confirmation link does not exist.')
    const link = order.contacts?.find((c) => c.channel !== 'ai_call' && c.link_expires_at)
    if (link?.link_expires_at && Date.parse(link.link_expires_at) < Date.now()) {
      throw new MockError(410, 'link_expired', 'This confirmation link expired 48 hours after it was sent.')
    }
    return order
  }

  confirmation(token: string): BuyerOrderView {
    const order = this.byToken(token)
    const responded = order.timeline?.find((e) => e.type === 'buyer_responded')
    const link = order.contacts?.find((c) => c.channel !== 'ai_call' && c.link_expires_at)
    return {
      shop_name: this.shop.name,
      order_ref: order.external_id ?? order.id,
      items: order.items.map((i) => ({ name: i.name, variant: i.variant, quantity: i.quantity })),
      cod_amount_vnd: order.cod_amount_vnd,
      recipient_name_masked: maskName(order.recipient_name ?? order.buyer_name),
      phone_masked: maskPhone(order.buyer_phone),
      address_masked: maskAddress(order.address.raw),
      expires_at: link?.link_expires_at ?? new Date(Date.now() + 48 * 3_600_000).toISOString(),
      allowed_actions:
        responded || !PRE_SHIP.includes(order.status)
          ? []
          : ['confirm', 'edit_address', 'cancel', 'not_ordered'],
      responded_action: responded
        ? ((order.contacts?.find((c) => c.channel !== 'ai_call')?.result as BuyerAction | undefined) ??
          'confirm')
        : null,
    }
  }

  respond(token: string, body: BuyerResponse): BuyerResponseResult {
    const order = this.byToken(token)
    if (order.timeline?.some((e) => e.type === 'buyer_responded') || !PRE_SHIP.includes(order.status)) {
      throw new MockError(409, 'link_already_used', 'This order has already been answered.')
    }
    const message: Record<BuyerAction, string> = {
      confirm: 'Cảm ơn bạn! Đơn hàng đã được xác nhận và sẽ sớm được gửi đi.',
      edit_address: 'Đã cập nhật địa chỉ giao hàng. Shop sẽ gửi đơn tới địa chỉ mới.',
      cancel: 'Đơn hàng đã được hủy. Cảm ơn bạn đã báo cho shop.',
      not_ordered:
        'Cảm ơn bạn đã báo. Đơn đã được hủy và số điện thoại này sẽ không bị liên hệ trong 30 ngày.',
    }
    order.contacts = order.contacts?.map((c) =>
      c.channel !== 'ai_call' ? { ...c, responded_at: nowIso(), result: body.action } : c,
    )
    this.event(order, 'buyer_responded', 'buyer', `Người mua chọn: ${BUYER_ACTION_VI[body.action]}.`)
    if (body.action === 'confirm') this.setStatus(order, 'cleared_to_ship')
    if (body.action === 'edit_address' && body.new_address) {
      order.address = body.new_address
      this.event(order, 'edited', 'buyer', 'Người mua sửa địa chỉ: chấm lại điểm.')
      this.setStatus(order, 'cleared_to_ship')
    }
    if (body.action === 'cancel') this.setStatus(order, 'cancelled')
    if (body.action === 'not_ordered') {
      this.blockedPhones.add(order.buyer_phone)
      this.setStatus(order, 'cancelled')
    }
    return { action: body.action, message_vi: message[body.action] }
  }

  // ── Delivery outcomes ──

  importDelivery(csv: string): DeliveryImportResult {
    const rows = parseCsv(csv)
    const header = rows.shift()?.map((h) => h.trim().toLowerCase()) ?? []
    const idCol = header.indexOf('order_id') >= 0 ? header.indexOf('order_id') : header.indexOf('external_id')
    const resultCol = header.indexOf('result')
    if (idCol < 0 || resultCol < 0) {
      throw new MockError(400, 'validation_error', 'CSV needs order_id (or external_id) and result columns.')
    }
    let applied = 0
    let unknown = 0
    const rejected: ImportRowError[] = []
    rows.forEach((row, index) => {
      if (row.every((cell) => !cell.trim())) return
      const ref = row[idCol]?.trim()
      const result = row[resultCol]?.trim()
      const order = [...this.orders.values()].find((o) => o.id === ref || o.external_id === ref)
      if (!order) return void unknown++
      if (!['delivered', 'refused', 'unreachable', 'carrier_issue', 'shop_issue'].includes(result ?? '')) {
        return void rejected.push({ row: index + 1, field: 'result', message: 'Kết quả giao không hợp lệ.' })
      }
      this.setStatus(order, result === 'delivered' ? 'delivered' : 'delivery_failed')
      this.event(
        order,
        'delivery_result',
        'carrier',
        result === 'delivered' ? 'Giao thành công, đã thu hộ.' : `Giao thất bại: ${result}.`,
      )
      applied++
    })
    return { received: applied + unknown + rejected.length, applied, unknown_orders: unknown, rejected }
  }

  // ── Dashboard ──

  dashboard(from: string, to: string): DashboardSummary {
    const start = Date.parse(from)
    const end = Date.parse(to) + 86_400_000 - 1
    const inRange = [...this.orders.values()].filter((o) => {
      const t = Date.parse(o.placed_at)
      return t >= start && t <= end
    })
    const counts = new Map<DecisionAction, number>()
    for (const o of inRange)
      if (o.decision) counts.set(o.decision.action, (counts.get(o.decision.action) ?? 0) + 1)
    const cancelled = inRange.filter((o) => o.status === 'cancelled').length
    const delivered = inRange.filter((o) => o.status === 'delivered').length
    const failed = inRange.filter((o) => o.status === 'delivery_failed').length
    const good = inRange.filter(
      (o) => o.status === 'delivered' || o.timeline?.some((e) => /Xác nhận/.test(e.message_vi)),
    )
    const goodContacted = good.filter((o) => (o.contacts?.length ?? 0) > 0)
    const cost = this.shop.settings.failed_delivery_cost_vnd ?? FAILED_DELIVERY_COST
    return {
      period_from: from,
      period_to: to,
      orders_screened: inRange.filter((o) => o.current_score).length,
      actions: ALL_ACTIONS.map((action) => ({ action, count: counts.get(action) ?? 0 })).filter(
        (a) => a.count > 0,
      ),
      cancelled_before_ship: cancelled,
      delivered,
      delivery_failed: failed,
      estimated_savings_vnd:
        cancelled * cost +
        Math.round(inRange.filter((o) => o.tier === 'very_high' || o.tier === 'high').length * cost * 0.35),
      good_orders_contacted_rate: good.length ? Number((goodContacted.length / good.length).toFixed(3)) : 0,
    }
  }

  backtest(): BacktestResult {
    const curve = (power: number) =>
      Array.from({ length: 11 }, (_, i) => {
        const x = i / 10
        return { contacted_share: x, failures_caught_share: Number(Math.min(1, x ** power).toFixed(3)) }
      })
    return {
      generated_at: '2026-10-12T09:00:00+07:00',
      dataset: 'Dữ liệu mô phỏng 12.000 đơn (synthetic, 90 ngày)',
      orders: 12_000,
      orders_per_day: 300,
      failed_delivery_cost_vnd: this.shop.settings.failed_delivery_cost_vnd ?? FAILED_DELIVERY_COST,
      lift: [
        { policy: 'cod_guard', points: curve(0.45) },
        { policy: 'phone_history_only', points: curve(0.7) },
        { policy: 'call_everyone', points: curve(1) },
      ],
      comparison: [
        { policy: 'do_nothing', contact_rate: 0, failures_caught_rate: 0, monthly_savings_vnd: 0 },
        {
          policy: 'call_everyone',
          contact_rate: 1,
          failures_caught_rate: 0.78,
          monthly_savings_vnd: 18_400_000,
        },
        { policy: 'deposit_all', contact_rate: 1, failures_caught_rate: 0.9, monthly_savings_vnd: 9_100_000 },
        {
          policy: 'phone_history_only',
          contact_rate: 0.18,
          failures_caught_rate: 0.41,
          monthly_savings_vnd: 14_700_000,
        },
        {
          policy: 'cod_guard',
          contact_rate: 0.24,
          failures_caught_rate: 0.67,
          monthly_savings_vnd: 27_900_000,
        },
      ],
    }
  }

  // ── Demo controls ──

  spamSimulation(): SpamSimulationResult {
    const phone = '+84000999999'
    const now = Date.now()
    for (let i = 0; i < 50; i++) {
      const id = `ord_spam_${String(i + 1).padStart(2, '0')}_${now}`
      const placed = new Date(now - (50 - i) * 15_000).toISOString()
      const base = seedData(this.seed + i + 1).orders[0]!
      this.orders.set(id, {
        ...base,
        id,
        external_id: `SPAM-${now % 10_000}-${i + 1}`,
        buyer_name: `Tài khoản ${(i % 20) + 1}`,
        buyer_phone: phone,
        status: i === 0 ? 'cancelled' : 'pending_review',
        tier: 'very_high',
        risk_score: 96,
        current_action: i === 0 ? 'ai_call' : 'hold_for_review',
        placed_at: placed,
        updated_at: placed,
        contacts: i === 0 ? base.contacts : [],
        calls: [],
        decision: base.decision && {
          ...base.decision,
          action: i === 0 ? 'ai_call' : 'hold_for_review',
          block_reasons: i === 0 ? [] : ['batched', 'phone_blocked'],
        },
        timeline: [
          {
            at: placed,
            type: 'decided',
            actor: 'engine',
            message_vi:
              i === 0
                ? 'AI gọi xác nhận (gộp 15 phút).'
                : 'Không liên hệ: SĐT đã gộp liên hệ rồi bị chặn sau "Tôi không đặt".',
          },
        ],
        allowed_overrides: ALL_ACTIONS,
        confirmation_token: null,
      })
    }
    this.blockedPhones.add(phone)
    return {
      orders_created: 50,
      accounts: 20,
      phone_masked: maskPhone(phone),
      contacts_made: 1,
      phone_blocked: true,
    }
  }
}

// ── Helpers ──

export const ACTION_VI: Record<DecisionAction, string> = {
  ship_now: 'Gửi ngay',
  send_confirmation_link: 'Gửi link xác nhận',
  ai_call: 'AI gọi',
  require_deposit: 'Yêu cầu cọc',
  hold_for_review: 'Chờ duyệt',
  cancel: 'Hủy đơn',
}

const BUYER_ACTION_VI: Record<BuyerAction, string> = {
  confirm: 'Xác nhận',
  edit_address: 'Sửa địa chỉ',
  cancel: 'Hủy',
  not_ordered: 'Tôi không đặt',
}

function statusFor(action: DecisionAction): OrderStatus {
  switch (action) {
    case 'ship_now':
      return 'cleared_to_ship'
    case 'send_confirmation_link':
    case 'ai_call':
      return 'awaiting_confirmation'
    case 'require_deposit':
      return 'awaiting_deposit'
    case 'hold_for_review':
      return 'pending_review'
    case 'cancel':
      return 'cancelled'
  }
}

export function toE164(raw: string): string | null {
  const digits = raw.replace(/\D/g, '')
  const national =
    digits.startsWith('84') && [11, 12].includes(digits.length)
      ? digits.slice(2)
      : digits.startsWith('0') && [10, 11].includes(digits.length)
        ? digits.slice(1)
        : null
  return national && /^\d{9,10}$/.test(national) ? `+84${national}` : null
}

function maskName(name: string): string {
  const parts = name.split(' ')
  return parts.map((p, i) => (i === parts.length - 1 ? p : `${p[0]}.`)).join(' ')
}

function maskAddress(raw: string): string {
  const parts = raw.split(',').map((p) => p.trim())
  return parts.length > 1 ? ['•••', ...parts.slice(1)].join(', ') : '•••'
}

/** Small RFC 4180 parser: quoted cells, doubled quotes, CRLF or LF. */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  const source = text.replace(/^﻿/, '')
  for (let i = 0; i < source.length; i++) {
    const c = source[i]!
    if (quoted) {
      if (c === '"' && source[i + 1] === '"') {
        cell += '"'
        i++
      } else if (c === '"') quoted = false
      else cell += c
    } else if (c === '"') quoted = true
    else if (c === ',') {
      row.push(cell)
      cell = ''
    } else if (c === '\n' || c === '\r') {
      if (c === '\r' && source[i + 1] === '\n') i++
      row.push(cell)
      rows.push(row)
      row = []
      cell = ''
    } else cell += c
  }
  if (cell || row.length) {
    row.push(cell)
    rows.push(row)
  }
  return rows
}

export const mockDb = new MockDb()
