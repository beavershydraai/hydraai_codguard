import type { PolicyComparison } from '@/api/gen'

export const PERIODS = [
  { value: '7', label: '7 days' },
  { value: '30', label: '30 days' },
  { value: '90', label: '90 days' },
] as const
export type Period = (typeof PERIODS)[number]['value']

export type Policy = PolicyComparison['policy']

export const POLICY_LABELS: Record<Policy, string> = {
  cod_guard: 'COD Guard',
  phone_history_only: 'Phone history only',
  call_everyone: 'Call everyone',
  do_nothing: 'Do nothing',
  deposit_all: 'Deposit for all',
}
