import { AlertCircle } from 'lucide-react'

import type { ProblemDetail } from '@/api/gen'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

// With `throwOnError`, the generated client throws the parsed problem+json body; a network
// failure throws an Error instead.
function isProblem(error: unknown): error is ProblemDetail {
  return typeof error === 'object' && error !== null && 'status' in error && 'title' in error
}

export function QueryError({ error }: { error: unknown }) {
  const notBuilt = isProblem(error) && error.code === 'not_implemented'
  const message = isProblem(error)
    ? (error.detail ?? error.title)
    : error instanceof Error
      ? error.message
      : String(error)
  return (
    <Alert variant="destructive">
      <AlertCircle />
      <AlertTitle>{notBuilt ? 'API chưa sẵn sàng' : 'Không tải được dữ liệu'}</AlertTitle>
      <AlertDescription>
        {notBuilt
          ? 'Backend chưa triển khai endpoint này. Chạy mock server (xem frontend/README.md).'
          : message}
      </AlertDescription>
    </Alert>
  )
}
