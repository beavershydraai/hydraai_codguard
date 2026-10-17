import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { QueryError } from './query-error'

describe('QueryError', () => {
  it('shows the problem detail', () => {
    render(
      <QueryError
        error={{
          type: 'about:blank',
          title: 'Not found',
          status: 404,
          code: 'not_found',
          detail: 'No such order.',
        }}
      />,
    )
    expect(screen.getByText('No such order.')).toBeInTheDocument()
  })

  it('never prints an empty error body as [object Object]', () => {
    render(<QueryError error={{}} />)
    expect(screen.queryByText('[object Object]')).not.toBeInTheDocument()
    expect(screen.getByText(/no details/)).toBeInTheDocument()
  })
})
