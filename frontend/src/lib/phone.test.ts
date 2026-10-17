import { describe, expect, it } from 'vitest'

import { toInternational } from './phone'

describe('toInternational', () => {
  it('keeps an international number', () => {
    expect(toInternational('+84000139824')).toBe('+84000139824')
    expect(toInternational('+6500012345')).toBe('+6500012345')
  })

  it('reads a national number as Vietnamese', () => {
    expect(toInternational('0000000001')).toBe('+84000000001')
  })

  it('gives nothing for text that is no phone number', () => {
    expect(toInternational('')).toBe('')
    expect(toInternational('abc')).toBe('')
  })
})
