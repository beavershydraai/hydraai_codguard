import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TierBadge } from './tier-badge'

describe('TierBadge', () => {
  it('shows the English tier label', () => {
    render(<TierBadge tier="very_high" />)
    expect(screen.getByText('Very high')).toBeInTheDocument()
  })
})
