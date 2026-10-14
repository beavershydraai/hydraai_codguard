import { describe, expect, it } from 'vitest'

import { formatVnd, ORDER_STATUS_LABELS } from './labels'

describe('labels', () => {
  it('names every order state from the domain rules', () => {
    expect(Object.values(ORDER_STATUS_LABELS)).toEqual([
      'New',
      'Cleared to ship',
      'Awaiting confirmation',
      'Awaiting deposit',
      'Pending review',
      'Cancelled',
      'Shipped',
      'Delivered',
      'Delivery failed',
    ])
  })

  it('formats integer VND', () => {
    expect(formatVnd(350000)).toBe('₫350,000')
  })
})
