import type { PolicyComparison } from '@/api/gen'

export const PERIODS = [
  { value: '7', label: '7 ngày' },
  { value: '30', label: '30 ngày' },
  { value: '90', label: '90 ngày' },
] as const
export type Period = (typeof PERIODS)[number]['value']

export type Policy = PolicyComparison['policy']

export const POLICY_LABELS: Record<Policy, string> = {
  cod_guard: 'COD Guard',
  phone_history_only: 'Chỉ dùng lịch sử SĐT',
  call_everyone: 'Gọi tất cả',
  do_nothing: 'Không làm gì',
  deposit_all: 'Cọc tất cả',
}
