import { describe, expect, it } from 'vitest'

import type { OrderSummary } from '@/api/gen'

import { ordersToCsv } from './orders-csv'

const order: OrderSummary = {
  id: 'ord_01',
  external_id: 'FB-1',
  channel: 'facebook',
  buyer_name: 'Nguyễn "Bé" A, Hà Nội',
  buyer_phone: '+84000000001',
  is_gift: false,
  total_vnd: 330000,
  cod_amount_vnd: 330000,
  status: 'awaiting_confirmation',
  tier: 'high',
  risk_score: 41,
  current_action: 'ai_call',
  placed_at: '2026-10-09T10:15:00+07:00',
  updated_at: '2026-10-09T10:16:00+07:00',
}

describe('ordersToCsv', () => {
  it('writes a BOM, an English header and quoted cells', () => {
    const csv = ordersToCsv([order])
    expect(csv.startsWith('﻿Order ID,Channel,')).toBe(true)
    expect(csv).toContain(
      'FB-1,Facebook,"Nguyễn ""Bé"" A, Hà Nội",+84000000001,330000,High,41,AI call,Awaiting confirmation,2026-10-09T10:15:00+07:00\r\n',
    )
  })
})
