import { describe, expect, it } from 'vitest'

import { safeRedirect } from './auth'

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
