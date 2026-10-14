/**
 * Synthetic demo data for the in-browser mock API. Deterministic for a given seed and reference
 * time, so a reset gives the same shop. Every name is generated, every phone uses the invalid
 * +84000… prefix, and no record describes a real person.
 */
import type {
  Call,
  CallOutcome,
  ContactAttempt,
  Decision,
  DecisionAction,
  HardRule,
  OrderDetail,
  OrderEvent,
  OrderItem,
  OrderStatus,
  Policy,
  Reason,
  RiskScore,
  RiskTier,
  SalesChannel,
  Shop,
  Signal,
} from '@/api/gen'

export const SHOP_ID = 'shop_demo'
export const FAILED_DELIVERY_COST = 60_000

export const DEFAULT_SETTINGS = {
  failed_delivery_cost_vnd: FAILED_DELIVERY_COST,
  ai_call_cost_vnd: 1_500,
  confirmation_link_cost_vnd: 300,
  deposit_request_cost_vnd: 5_000,
  contact_hours: { start: '08:00', end: '21:00' },
} satisfies Shop['settings']

export function defaultPolicy(effectiveFrom: string): Policy {
  return {
    version: 1,
    effective_from: effectiveFrom,
    updated_by: 'system',
    tiers: [
      { tier: 'low', action: 'ship_now', if_no_response: null, no_response_after_minutes: null },
      {
        tier: 'medium',
        action: 'send_confirmation_link',
        if_no_response: 'ai_call',
        no_response_after_minutes: 120,
      },
      { tier: 'high', action: 'ai_call', if_no_response: 'hold_for_review', no_response_after_minutes: 30 },
      {
        tier: 'very_high',
        action: 'require_deposit',
        if_no_response: 'hold_for_review',
        no_response_after_minutes: 1440,
      },
    ],
  }
}

// ── Random helpers ──

export function rng(seed: number) {
  let a = seed >>> 0
  const next = () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
  return {
    next,
    int: (min: number, max: number) => min + Math.floor(next() * (max - min + 1)),
    pick: <T>(list: readonly T[]): T => list[Math.floor(next() * list.length)]!,
    chance: (p: number) => next() < p,
  }
}
type Rng = ReturnType<typeof rng>

export function tierFor(probability: number): RiskTier {
  return probability < 0.08 ? 'low' : probability < 0.2 ? 'medium' : probability < 0.4 ? 'high' : 'very_high'
}

export const TIER_ACTION: Record<RiskTier, DecisionAction> = {
  low: 'ship_now',
  medium: 'send_confirmation_link',
  high: 'ai_call',
  very_high: 'require_deposit',
}

export function maskPhone(phone: string): string {
  return phone.length > 7 ? `${phone.slice(0, 6)}•••${phone.slice(-3)}` : '•••'
}

const iso = (ms: number) => new Date(ms).toISOString()
const MIN = 60_000
const HOUR = 60 * MIN
const DAY = 24 * HOUR

// ── Catalogue ──

const FAMILY = [
  'Nguyễn',
  'Trần',
  'Lê',
  'Phạm',
  'Hoàng',
  'Huỳnh',
  'Phan',
  'Vũ',
  'Võ',
  'Đặng',
  'Bùi',
  'Đỗ',
  'Hồ',
  'Ngô',
  'Dương',
]
const MIDDLE = ['Văn', 'Thị', 'Minh', 'Thu', 'Ngọc', 'Hoàng', 'Thanh', 'Gia', 'Bảo', 'Quốc', 'Khánh']
const GIVEN = [
  'An',
  'Bình',
  'Châu',
  'Dũng',
  'Giang',
  'Hà',
  'Hải',
  'Hương',
  'Khánh',
  'Lan',
  'Linh',
  'Long',
  'Mai',
  'Nam',
  'Ngân',
  'Phúc',
  'Quân',
  'Tâm',
  'Thảo',
  'Trang',
  'Tuấn',
  'Vy',
  'Yến',
]

const PLACES = [
  { ward: 'phường Cầu Giấy', province: 'Hà Nội' },
  { ward: 'phường Hoàn Kiếm', province: 'Hà Nội' },
  { ward: 'phường Bến Thành', province: 'TP Hồ Chí Minh' },
  { ward: 'phường Thủ Đức', province: 'TP Hồ Chí Minh' },
  { ward: 'phường Hải Châu', province: 'Đà Nẵng' },
  { ward: 'phường Ninh Kiều', province: 'Cần Thơ' },
  { ward: 'xã Tân Hiệp', province: 'An Giang' },
  { ward: 'phường Thủ Dầu Một', province: 'TP Hồ Chí Minh' },
  { ward: 'xã Đông Anh', province: 'Hà Nội' },
  { ward: 'phường Vinh Tân', province: 'Nghệ An' },
]

const PRODUCTS: { sku: string; name: string; variants: string[]; price: number }[] = [
  { sku: 'AT-01', name: 'Áo thun cotton', variants: ['Trắng / M', 'Đen / L', 'Be / S'], price: 189_000 },
  { sku: 'VH-02', name: 'Váy hoa nhí', variants: ['Xanh / M', 'Hồng / S'], price: 329_000 },
  { sku: 'QJ-03', name: 'Quần jean ống rộng', variants: ['28', '30', '32'], price: 359_000 },
  { sku: 'AK-04', name: 'Áo khoác gió', variants: ['Đen / L', 'Xám / XL'], price: 429_000 },
  { sku: 'TT-05', name: 'Túi tote canvas', variants: ['Kem', 'Đen'], price: 159_000 },
  { sku: 'GS-06', name: 'Giày sneaker trắng', variants: ['38', '39', '40', '41'], price: 549_000 },
  { sku: 'DN-07', name: 'Set đồ ngủ lụa', variants: ['Hồng / M', 'Xanh / L'], price: 279_000 },
]

const CHANNEL_NAME: Record<SalesChannel, string> = {
  facebook: 'Facebook',
  tiktok: 'TikTok',
  zalo: 'Zalo',
  website: 'website',
  other: 'kênh khác',
}

const CHANNEL_PREFIX: Record<SalesChannel, string> = {
  facebook: 'FB',
  tiktok: 'TT',
  zalo: 'ZL',
  website: 'WEB',
  other: 'OT',
}

// ── Signals and reasons (every reason points at a signal that is present) ──

type SignalSpec = Omit<Signal, 'value' | 'contribution'> & {
  value: (r: Rng, o: { cod: number }) => Signal['value']
  contribution: number
  reason?: (value: Signal['value']) => string
}

const RISK_SIGNALS: SignalSpec[] = [
  {
    key: 'phone_return_rate',
    group: 'phone_history',
    label_vi: 'Tỷ lệ hoàn của SĐT',
    value: (r) => `${r.int(2, 4)}/${r.int(4, 5)} đơn`,
    contribution: 0.22,
    reason: (v) => `SĐT này đã hoàn ${v} gần nhất.`,
  },
  {
    key: 'velocity_same_phone',
    group: 'velocity',
    label_vi: 'Đơn cùng SĐT trong 24 giờ',
    value: (r) => r.int(2, 4),
    contribution: 0.16,
    reason: (v) => `Có ${v} đơn cùng SĐT trong 24 giờ qua.`,
  },
  {
    key: 'address_vague',
    group: 'address_quality',
    label_vi: 'Địa chỉ thiếu số nhà hoặc ngõ',
    value: () => true,
    contribution: 0.12,
    reason: () => 'Địa chỉ thiếu số nhà, shipper khó tìm.',
  },
  {
    key: 'phone_first_order',
    group: 'phone_history',
    label_vi: 'SĐT mua lần đầu',
    value: () => true,
    contribution: 0.05,
    reason: () => 'Đây là đơn đầu tiên của số điện thoại này.',
  },
  {
    key: 'order_night',
    group: 'order_behavior',
    label_vi: 'Đặt hàng lúc nửa đêm',
    value: (r) => `0${r.int(0, 3)}:${r.int(10, 59)}`,
    contribution: 0.05,
    reason: (v) => `Đơn đặt lúc ${v}, khung giờ có tỷ lệ bom cao.`,
  },
  {
    key: 'cod_high',
    group: 'payment',
    label_vi: 'Giá trị thu hộ cao',
    value: (_r, o) => o.cod,
    contribution: 0.07,
    reason: (v) => `Giá trị thu hộ cao (${Number(v).toLocaleString('vi-VN')} ₫).`,
  },
  {
    key: 'rushed_chat',
    group: 'conversation',
    label_vi: 'Chốt đơn vội, không hỏi size hay giá',
    value: () => true,
    contribution: 0.06,
    reason: () => 'Khách chốt rất nhanh, không hỏi size hay giá.',
  },
  {
    key: 'livestream',
    group: 'context',
    label_vi: 'Chốt đơn trong livestream',
    value: () => true,
    contribution: 0.04,
    reason: () => 'Đơn chốt trong livestream, nhóm có tỷ lệ bom cao hơn.',
  },
  {
    key: 'name_mismatch',
    group: 'conversation',
    label_vi: 'Tên người nhận khác tên tài khoản chat',
    value: () => true,
    contribution: 0.05,
    reason: () => 'Tên người nhận khác tên tài khoản đặt hàng.',
  },
]

const SAFE_SIGNALS: SignalSpec[] = [
  {
    key: 'phone_delivered',
    group: 'phone_history',
    label_vi: 'Đơn giao thành công trước đó',
    value: (r) => r.int(2, 9),
    contribution: -0.1,
    reason: (v) => `Khách quen: ${v} đơn trước đều giao thành công.`,
  },
  {
    key: 'address_complete',
    group: 'address_quality',
    label_vi: 'Địa chỉ đầy đủ số nhà, phường',
    value: () => true,
    contribution: -0.04,
  },
  {
    key: 'asked_details',
    group: 'conversation',
    label_vi: 'Hỏi kỹ size và màu trước khi chốt',
    value: () => true,
    contribution: -0.03,
  },
]

function buildSignals(r: Rng, probability: number, cod: number): { signals: Signal[]; reasons: Reason[] } {
  const risky = probability >= 0.08
  const pool = risky ? [...RISK_SIGNALS] : [...SAFE_SIGNALS]
  const count = risky ? (probability >= 0.4 ? 4 : 3) : 2
  const chosen: SignalSpec[] = []
  while (chosen.length < count && pool.length) chosen.push(pool.splice(r.int(0, pool.length - 1), 1)[0]!)
  const signals = chosen
    .map((spec) => ({
      key: spec.key,
      group: spec.group,
      label_vi: spec.label_vi,
      value: spec.value(r, { cod }),
      contribution: Number((spec.contribution * (0.7 + r.next() * 0.6)).toFixed(3)),
    }))
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
  const reasons = signals
    .map((signal) => {
      const spec = chosen.find((s) => s.key === signal.key)!
      return spec.reason ? { text_vi: spec.reason(signal.value), signal_keys: [signal.key] } : null
    })
    .filter((reason): reason is Reason => reason !== null)
    .slice(0, 3)
  return { signals, reasons }
}

// ── Scenarios: how far an order got and how it ended ──

type Scenario =
  | 'new'
  | 'ship'
  | 'shipped'
  | 'delivered'
  | 'failed'
  | 'link_waiting'
  | 'link_confirmed'
  | 'link_no_response_call'
  | 'call_queued'
  | 'call_confirmed'
  | 'call_edited'
  | 'call_cancelled'
  | 'call_not_ordered'
  | 'call_no_answer_review'
  | 'deposit_waiting'
  | 'deposit_unpaid_review'
  | 'deposit_paid'
  | 'prepaid_skip'
  | 'invalid_phone'
  | 'staff_override'

function probabilityFor(r: Rng, scenario: Scenario): number {
  const band = (min: number, max: number) => min + r.next() * (max - min)
  switch (scenario) {
    case 'ship':
    case 'shipped':
    case 'delivered':
      return band(0.01, 0.075)
    case 'failed':
      return band(0.03, 0.18)
    case 'link_waiting':
    case 'link_confirmed':
    case 'link_no_response_call':
      return band(0.085, 0.19)
    case 'call_queued':
    case 'call_confirmed':
    case 'call_edited':
    case 'call_cancelled':
    case 'call_not_ordered':
    case 'call_no_answer_review':
    case 'staff_override':
      return band(0.21, 0.39)
    case 'deposit_waiting':
    case 'deposit_unpaid_review':
    case 'deposit_paid':
      return band(0.41, 0.82)
    default:
      return band(0.05, 0.3)
  }
}

const SCENARIO_MIX: [Scenario, number][] = [
  ['new', 2],
  ['ship', 8],
  ['shipped', 7],
  ['delivered', 14],
  ['failed', 4],
  ['link_waiting', 5],
  ['link_confirmed', 5],
  ['link_no_response_call', 2],
  ['call_queued', 2],
  ['call_confirmed', 5],
  ['call_edited', 2],
  ['call_cancelled', 2],
  ['call_not_ordered', 2],
  ['call_no_answer_review', 3],
  ['deposit_waiting', 4],
  ['deposit_unpaid_review', 3],
  ['deposit_paid', 2],
  ['prepaid_skip', 4],
  ['invalid_phone', 2],
  ['staff_override', 2],
]

const CALL_SUMMARY: Record<CallOutcome, string> = {
  confirmed: 'Khách xác nhận đúng sản phẩm, size và địa chỉ; hẹn nhận hàng giờ hành chính.',
  edited: 'Khách xác nhận đơn và đổi địa chỉ giao sang chỗ làm; AI đã đọc lại địa chỉ mới.',
  cancelled: 'Khách đổi ý, không muốn nhận hàng nữa và xác nhận hủy đơn.',
  not_ordered: 'Người nghe máy nói không đặt đơn này. Số điện thoại đã bị chặn liên hệ 30 ngày.',
  no_answer: 'Không nghe máy.',
  wrong_person: 'Người nghe máy không phải người đặt hàng.',
  unclear: 'Cuộc gọi bị ngắt giữa chừng, chưa rõ khách có nhận hàng không.',
}

export type MockOrder = OrderDetail & {
  /** Confirmation link token for the buyer page, when a link was sent. */
  confirmation_token?: string | null
}

export type SeedResult = {
  orders: MockOrder[]
  calls: Call[]
  shop: Shop
  policies: Policy[]
}

export function seedData(seed = 2026, now = Date.now()): SeedResult {
  const r = rng(seed)
  const orders: MockOrder[] = []
  const calls: Call[] = []
  const scenarios = SCENARIO_MIX.flatMap(([scenario, n]) => Array<Scenario>(n).fill(scenario))
  // Shuffle so neighbouring rows differ, deterministically.
  for (let i = scenarios.length - 1; i > 0; i--) {
    const j = r.int(0, i)
    ;[scenarios[i], scenarios[j]] = [scenarios[j]!, scenarios[i]!]
  }
  const sequence = new Map<SalesChannel, number>()
  const policyStart = iso(now - 30 * DAY)

  scenarios.forEach((scenario, index) => {
    const channel = r.pick<SalesChannel>(['facebook', 'facebook', 'tiktok', 'tiktok', 'zalo', 'website'])
    const seq = (sequence.get(channel) ?? 1000) + 1
    sequence.set(channel, seq)
    const externalId = `${CHANNEL_PREFIX[channel]}-${seq}`
    const orderId = `ord_mock_${String(index + 1).padStart(3, '0')}`

    const name = `${r.pick(FAMILY)} ${r.pick(MIDDLE)} ${r.pick(GIVEN)}`
    const phone =
      scenario === 'invalid_phone'
        ? `0${r.int(100, 999)}${r.int(10, 99)}`
        : `+84000${String(r.int(0, 999_999)).padStart(6, '0')}`
    const place = r.pick(PLACES)
    const vague = r.chance(0.2)
    const address = {
      raw: vague
        ? `Gần chợ ${place.ward.replace(/^(phường|xã) /, '')}, ${place.province}`
        : `Số ${r.int(1, 199)} ngõ ${r.int(1, 99)}, ${place.ward}, ${place.province}`,
      street: vague ? null : `Số ${r.int(1, 199)} ngõ ${r.int(1, 99)}`,
      ward: place.ward,
      province: place.province,
    }

    const items: OrderItem[] = Array.from({ length: r.int(1, 2) }, () => {
      const product = r.pick(PRODUCTS)
      return {
        sku: product.sku,
        name: product.name,
        variant: r.pick(product.variants),
        quantity: r.int(1, 2),
        unit_price_vnd: product.price,
      }
    })
    const shipping = r.pick([20_000, 25_000, 30_000])
    const discount = r.chance(0.3) ? r.pick([10_000, 20_000, 50_000]) : 0
    const subtotal = items.reduce((sum, item) => sum + item.quantity * item.unit_price_vnd, 0)
    const total = subtotal - discount + shipping
    const prepaid =
      scenario === 'prepaid_skip'
        ? total
        : scenario === 'deposit_paid'
          ? Math.round((total * 0.3) / 1000) * 1000
          : r.chance(0.1)
            ? 100_000
            : 0
    const cod = Math.max(total - prepaid, 0)

    // Placing time: recent scenarios are fresh, finished ones are older.
    const ageHours =
      scenario === 'new'
        ? r.next() * 0.3
        : ['link_waiting', 'call_queued', 'deposit_waiting', 'ship'].includes(scenario)
          ? 0.5 + r.next() * 20
          : ['delivered', 'failed'].includes(scenario)
            ? 48 + r.next() * 24 * 12
            : 6 + r.next() * 24 * 4
    const placed = now - ageHours * HOUR
    let t = placed
    const at = (minutes: number) => {
      t += minutes * MIN
      return iso(Math.min(t, now - MIN))
    }

    const timeline: OrderEvent[] = [
      {
        at: iso(placed),
        type: 'created',
        actor: 'system',
        message_vi: `Nhận đơn từ ${CHANNEL_NAME[channel]}.`,
      },
    ]
    let status: OrderStatus = 'new'
    let score: RiskScore | null = null
    let decision: Decision | null = null
    const contacts: ContactAttempt[] = []
    const orderCalls: Call[] = []
    let confirmationToken: string | null = null
    const hardRules: HardRule[] = []

    if (scenario !== 'new') {
      const probability = scenario === 'prepaid_skip' ? 0 : probabilityFor(r, scenario)
      const scoredAt = at(1)
      if (scenario === 'invalid_phone') hardRules.push('invalid_phone')
      const skipped = scenario === 'prepaid_skip'
      const tier: RiskTier | null = skipped ? null : tierFor(probability)
      const { signals, reasons } =
        skipped || scenario === 'invalid_phone'
          ? { signals: [], reasons: [] }
          : buildSignals(r, probability, cod)
      const invalidReason: Reason[] =
        scenario === 'invalid_phone'
          ? [
              {
                text_vi: 'Số điện thoại không đúng định dạng nên không liên hệ được.',
                signal_keys: ['phone_invalid'],
              },
            ]
          : []
      const invalidSignal: Signal[] =
        scenario === 'invalid_phone'
          ? [
              {
                key: 'phone_invalid',
                group: 'phone_history',
                label_vi: 'SĐT không hợp lệ',
                value: phone,
                contribution: 0,
              },
            ]
          : []
      score = {
        id: `scr_${orderId}_1`,
        scored_at: scoredAt,
        status: skipped ? 'skipped' : 'scored',
        skipped_reason: skipped ? 'prepaid_skip' : null,
        probability: skipped ? null : Number(probability.toFixed(3)),
        risk_score: skipped ? null : Math.round(probability * 100),
        tier,
        expected_loss_vnd: skipped ? null : Math.round(probability * FAILED_DELIVERY_COST),
        failed_delivery_cost_vnd: FAILED_DELIVERY_COST,
        hard_rules: skipped ? ['prepaid_skip'] : hardRules,
        top_signals: [...invalidSignal, ...signals],
        reasons: [...invalidReason, ...reasons].slice(0, 3),
        model_version: 'cod-guard-gbm-2026.10',
      }
      timeline.push({
        at: scoredAt,
        type: 'scored',
        actor: 'engine',
        message_vi: skipped
          ? 'Đơn đã trả trước toàn bộ: bỏ qua chấm điểm.'
          : `Chấm điểm rủi ro ${score.risk_score}/100 (${tier}).`,
      })

      const action: DecisionAction =
        scenario === 'invalid_phone' ? 'hold_for_review' : skipped || !tier ? 'ship_now' : TIER_ACTION[tier]
      const decidedAt = at(1)
      decision = {
        decided_at: decidedAt,
        action,
        policy_version: 1,
        expected_loss_vnd: score.expected_loss_vnd ?? null,
        contact_cost_vnd:
          action === 'ai_call'
            ? 1_500
            : action === 'send_confirmation_link'
              ? 300
              : action === 'require_deposit'
                ? 5_000
                : null,
        block_reasons: [],
        next_action: null,
        next_action_at: null,
        decided_by: 'engine',
      }
      timeline.push({ at: decidedAt, type: 'decided', actor: 'engine', message_vi: decisionMessage(action) })

      const call = (outcome: CallOutcome | null, attempt = 1): Call => {
        const queuedAt = at(2)
        const started = outcome ? at(1) : null
        const duration =
          outcome && outcome !== 'no_answer' ? r.int(45, 160) : outcome === 'no_answer' ? 0 : null
        const ended = outcome ? at(Math.max(1, Math.round((duration ?? 30) / 60))) : null
        const c: Call = {
          id: `call_${orderId}_${attempt}`,
          order_ids: [orderId],
          phone_masked: maskPhone(phone),
          status: outcome ? 'completed' : 'queued',
          attempt,
          queued_at: queuedAt,
          started_at: started,
          ended_at: ended,
          duration_seconds: duration,
          outcome,
          changes:
            outcome === 'edited'
              ? [
                  {
                    order_id: orderId,
                    field: 'delivery_address',
                    new_value: `Tòa nhà văn phòng, ${place.ward}, ${place.province}`,
                  },
                ]
              : [],
          cancel_reason: outcome === 'cancelled' ? 'Khách đổi ý, không cần nữa.' : null,
          human_callback_requested: false,
          buyer_requests: outcome === 'confirmed' && r.chance(0.4) ? 'Giao giờ hành chính' : null,
          summary_vi: outcome ? CALL_SUMMARY[outcome] : null,
        }
        orderCalls.push(c)
        contacts.push({
          id: `ct_${orderId}_${contacts.length + 1}`,
          channel: 'ai_call',
          created_at: queuedAt,
          call_id: c.id,
          responded_at: outcome && outcome !== 'no_answer' ? ended : null,
          result: outcome,
        })
        timeline.push({
          at: queuedAt,
          type: 'contact_started',
          actor: 'engine',
          message_vi: `AI gọi xác nhận (lần ${attempt}).`,
        })
        if (outcome) {
          timeline.push({
            at: ended!,
            type: 'call_completed',
            actor: 'ai_call',
            message_vi: `Kết quả cuộc gọi: ${CALL_OUTCOME_VI[outcome]}.`,
          })
        }
        return c
      }
      const link = (responded: boolean) => {
        const sentAt = at(1)
        confirmationToken = `cf_${orderId.slice(-3)}${r.int(1000, 9999)}`
        contacts.push({
          id: `ct_${orderId}_${contacts.length + 1}`,
          channel: 'confirmation_link',
          created_at: sentAt,
          link_expires_at: iso(Date.parse(sentAt) + 48 * HOUR),
          responded_at: responded ? at(r.int(5, 90)) : null,
          result: responded ? 'confirm' : null,
        })
        timeline.push({
          at: sentAt,
          type: 'contact_started',
          actor: 'engine',
          message_vi: 'Gửi link xác nhận qua Zalo ZNS (mock).',
        })
        if (responded) {
          timeline.push({
            at: at(0),
            type: 'buyer_responded',
            actor: 'buyer',
            message_vi: 'Người mua xác nhận đơn trên trang xác nhận.',
          })
        }
      }
      const deposit = (paid: boolean | null) => {
        const sentAt = at(1)
        confirmationToken = `cf_${orderId.slice(-3)}${r.int(1000, 9999)}`
        contacts.push({
          id: `ct_${orderId}_${contacts.length + 1}`,
          channel: 'deposit_request',
          created_at: sentAt,
          link_expires_at: iso(Date.parse(sentAt) + 24 * HOUR),
          responded_at: paid ? at(r.int(10, 200)) : null,
          result: paid ? 'paid' : paid === false ? 'unpaid' : null,
        })
        timeline.push({
          at: sentAt,
          type: 'contact_started',
          actor: 'engine',
          message_vi: 'Gửi yêu cầu đặt cọc (mock).',
        })
      }
      const ship = (delivered: boolean | null) => {
        status = 'cleared_to_ship'
        timeline.push({
          at: at(r.int(5, 60)),
          type: 'status_changed',
          actor: 'system',
          message_vi: 'Đơn được gửi đi.',
        })
        if (delivered === null) return
        status = 'shipped'
        timeline.push({
          at: at(r.int(60, 600)),
          type: 'status_changed',
          actor: 'carrier',
          message_vi: 'Đã bàn giao cho GHN.',
        })
        if (!delivered && !['shipped'].includes(scenario)) {
          status = 'delivery_failed'
          timeline.push({
            at: at(r.int(1_000, 3_000)),
            type: 'delivery_result',
            actor: 'carrier',
            message_vi: 'Giao thất bại: người mua từ chối nhận.',
          })
        } else if (delivered) {
          status = 'delivered'
          timeline.push({
            at: at(r.int(1_000, 3_000)),
            type: 'delivery_result',
            actor: 'carrier',
            message_vi: 'Giao thành công, đã thu hộ.',
          })
        }
      }

      switch (scenario) {
        case 'ship':
        case 'prepaid_skip':
          ship(scenario === 'prepaid_skip' && r.chance(0.5) ? true : null)
          break
        case 'shipped':
          ship(null)
          status = 'shipped'
          timeline.push({
            at: at(r.int(60, 600)),
            type: 'status_changed',
            actor: 'carrier',
            message_vi: 'Đã bàn giao cho GHN.',
          })
          break
        case 'delivered':
          ship(true)
          break
        case 'failed':
          ship(false)
          break
        case 'link_waiting':
          link(false)
          status = 'awaiting_confirmation'
          decision.next_action = 'ai_call'
          decision.next_action_at = iso(Date.parse(decidedAt) + 120 * MIN)
          break
        case 'link_confirmed':
          link(true)
          ship(r.chance(0.5) ? true : null)
          break
        case 'link_no_response_call':
          link(false)
          timeline.push({
            at: at(120),
            type: 'status_changed',
            actor: 'engine',
            message_vi: 'Không phản hồi sau 2 giờ: chuyển sang AI gọi.',
          })
          call('confirmed')
          ship(null)
          break
        case 'call_queued':
          call(null)
          status = 'awaiting_confirmation'
          break
        case 'call_confirmed':
          call('confirmed')
          ship(r.chance(0.5) ? true : null)
          break
        case 'call_edited':
          call('edited')
          timeline.push({
            at: at(1),
            type: 'edited',
            actor: 'ai_call',
            message_vi: 'Cập nhật địa chỉ theo cuộc gọi; chấm lại điểm.',
          })
          ship(null)
          break
        case 'call_cancelled':
          call('cancelled')
          status = 'cancelled'
          timeline.push({
            at: at(1),
            type: 'status_changed',
            actor: 'buyer',
            message_vi: 'Đơn bị hủy theo yêu cầu của người mua.',
          })
          break
        case 'call_not_ordered':
          call('not_ordered')
          status = 'cancelled'
          timeline.push({
            at: at(1),
            type: 'status_changed',
            actor: 'buyer',
            message_vi: 'Người nghe máy báo không đặt: hủy đơn, chặn SĐT 30 ngày.',
          })
          break
        case 'call_no_answer_review':
          call('no_answer', 1)
          t += 30 * MIN
          call('no_answer', 2)
          status = 'pending_review'
          decision.next_action = 'hold_for_review'
          timeline.push({
            at: at(1),
            type: 'status_changed',
            actor: 'engine',
            message_vi: 'Gọi 2 lần không nghe máy: chuyển chờ duyệt.',
          })
          break
        case 'deposit_waiting':
          deposit(null)
          status = 'awaiting_deposit'
          decision.next_action = 'hold_for_review'
          decision.next_action_at = iso(Date.parse(decidedAt) + 1440 * MIN)
          break
        case 'deposit_unpaid_review':
          deposit(false)
          status = 'pending_review'
          timeline.push({
            at: at(1440),
            type: 'status_changed',
            actor: 'engine',
            message_vi: 'Chưa đặt cọc sau 24 giờ: chuyển chờ duyệt.',
          })
          break
        case 'deposit_paid':
          deposit(true)
          timeline.push({
            at: at(1),
            type: 'buyer_responded',
            actor: 'buyer',
            message_vi: 'Người mua đã đặt cọc 30%.',
          })
          ship(null)
          break
        case 'invalid_phone':
          status = 'pending_review'
          break
        case 'staff_override': {
          call('unclear')
          status = 'pending_review'
          const overrideAt = at(r.int(10, 120))
          decision = { ...decision, decided_at: overrideAt, action: 'ship_now', decided_by: 'staff' }
          timeline.push({
            at: overrideAt,
            type: 'override',
            actor: 'admin@gmail.com',
            message_vi: 'Nhân viên chọn: Gửi ngay.',
            reason: 'Khách quen, đã gọi lại xác nhận qua Zalo.',
          })
          ship(null)
          break
        }
      }
    }

    const preShip = [
      'new',
      'cleared_to_ship',
      'awaiting_confirmation',
      'awaiting_deposit',
      'pending_review',
    ].includes(status)
    const lastAt = timeline[timeline.length - 1]!.at
    orders.push({
      id: orderId,
      external_id: externalId,
      channel,
      buyer_name: name,
      buyer_phone: phone,
      is_gift: r.chance(0.08),
      recipient_name: r.chance(0.1) ? `${r.pick(FAMILY)} ${r.pick(GIVEN)}` : null,
      recipient_phone: null,
      total_vnd: total,
      cod_amount_vnd: cod,
      status,
      tier: score?.tier ?? null,
      risk_score: score?.risk_score ?? null,
      current_action: decision?.action ?? null,
      placed_at: iso(placed),
      updated_at: lastAt,
      address,
      items,
      shipping_fee_vnd: shipping,
      discount_vnd: discount,
      prepaid_vnd: prepaid,
      note: r.chance(0.15) ? 'Gọi trước khi giao' : null,
      current_score: score,
      score_history: score ? [score] : [],
      decision,
      contacts,
      calls: orderCalls,
      timeline: [...timeline].reverse(),
      allowed_overrides: preShip ? ALL_ACTIONS.filter((a) => a !== decision?.action) : [],
      confirmation_token: confirmationToken,
    })
    calls.push(...orderCalls)
  })

  orders.sort((a, b) => b.placed_at.localeCompare(a.placed_at))
  return {
    orders,
    calls,
    shop: {
      id: SHOP_ID,
      name: 'Shop Thời Trang Mẫu',
      created_at: policyStart,
      settings: DEFAULT_SETTINGS,
      intake_api_key_last4: 'demo',
    },
    policies: [defaultPolicy(policyStart)],
  }
}

export const ALL_ACTIONS: DecisionAction[] = [
  'ship_now',
  'send_confirmation_link',
  'ai_call',
  'require_deposit',
  'hold_for_review',
  'cancel',
]

export const CALL_OUTCOME_VI: Record<CallOutcome, string> = {
  confirmed: 'Xác nhận',
  edited: 'Đã sửa',
  cancelled: 'Hủy',
  not_ordered: 'Không đặt',
  no_answer: 'Không nghe máy',
  wrong_person: 'Nhầm người',
  unclear: 'Không rõ',
}

export function decisionMessage(action: DecisionAction): string {
  switch (action) {
    case 'ship_now':
      return 'Quyết định: gửi ngay.'
    case 'send_confirmation_link':
      return 'Quyết định: gửi link xác nhận, gọi AI nếu 2 giờ không phản hồi.'
    case 'ai_call':
      return 'Quyết định: AI gọi xác nhận.'
    case 'require_deposit':
      return 'Quyết định: yêu cầu đặt cọc.'
    case 'hold_for_review':
      return 'Quyết định: chờ shop duyệt.'
    case 'cancel':
      return 'Quyết định: hủy đơn.'
  }
}
