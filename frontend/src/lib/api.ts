import type { QueryClient } from '@tanstack/react-query'

import type { ProblemDetail } from '@/api/gen'

const MESSAGES: Partial<Record<string, string>> = {
  order_not_editable: 'Đơn đã gửi đi nên không sửa được nữa.',
  contact_blocked: 'Không liên hệ được với người mua lúc này.',
  link_expired: 'Link xác nhận đã hết hạn.',
  link_already_used: 'Đơn này đã được phản hồi.',
  not_found: 'Không tìm thấy dữ liệu.',
  unauthorized: 'Phiên đăng nhập đã hết hạn.',
  forbidden: 'Bạn không có quyền thực hiện thao tác này.',
  rate_limited: 'Thao tác quá nhanh, vui lòng thử lại sau ít phút.',
}

export function isProblem(error: unknown): error is ProblemDetail {
  return typeof error === 'object' && error !== null && 'status' in error && 'code' in error
}

/** A Vietnamese message for an API error, for toasts and inline alerts. */
export function problemMessage(error: unknown, fallback = 'Có lỗi xảy ra, vui lòng thử lại.'): string {
  if (isProblem(error)) return MESSAGES[error.code] ?? error.detail ?? fallback
  return fallback
}

/** Refetches every query built from one of the given operations, e.g. after a mutation. */
export function invalidate(queryClient: QueryClient, ...operations: string[]) {
  return queryClient.invalidateQueries({
    predicate: (query) => operations.includes((query.queryKey[0] as { _id?: string } | undefined)?._id ?? ''),
  })
}
