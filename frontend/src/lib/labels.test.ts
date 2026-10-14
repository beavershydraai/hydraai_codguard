import { describe, expect, it } from 'vitest'

import { formatVnd, ORDER_STATUS_LABELS } from './labels'

describe('labels', () => {
  it('uses the Vietnamese order states from the domain rules', () => {
    expect(Object.values(ORDER_STATUS_LABELS)).toEqual([
      'Mới',
      'Được gửi',
      'Chờ xác nhận',
      'Chờ cọc',
      'Chờ duyệt',
      'Đã hủy',
      'Đã gửi',
      'Giao thành công',
      'Giao thất bại',
    ])
  })

  it('formats integer VND', () => {
    expect(formatVnd(350000).replace(/\s/g, ' ')).toBe('350.000 ₫')
  })
})
