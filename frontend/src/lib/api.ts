import type { QueryClient } from '@tanstack/react-query'

import type { ProblemDetail } from '@/api/gen'

const MESSAGES: Partial<Record<string, string>> = {
  order_not_editable: 'The order has already shipped, so it can no longer be edited.',
  contact_blocked: 'The buyer cannot be contacted right now.',
  link_expired: 'The confirmation link has expired.',
  link_already_used: 'This order has already been answered.',
  not_found: 'Not found.',
  unauthorized: 'Your session has expired.',
  forbidden: 'You do not have permission to do this.',
  rate_limited: 'Too many requests. Please try again in a few minutes.',
}

export function isProblem(error: unknown): error is ProblemDetail {
  return typeof error === 'object' && error !== null && 'status' in error && 'code' in error
}

/** An English message for an API error, for toasts and inline alerts. */
export function problemMessage(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (isProblem(error)) return MESSAGES[error.code] ?? error.detail ?? fallback
  return fallback
}

/** Refetches every query built from one of the given operations, e.g. after a mutation. */
export function invalidate(queryClient: QueryClient, ...operations: string[]) {
  return queryClient.invalidateQueries({
    predicate: (query) => operations.includes((query.queryKey[0] as { _id?: string } | undefined)?._id ?? ''),
  })
}
