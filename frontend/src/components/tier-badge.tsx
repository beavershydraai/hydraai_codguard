import type { ComponentProps } from 'react'

import type { RiskTier } from '@/api/gen'
import { Badge } from '@/components/reui/badge'
import { RISK_TIER_LABELS } from '@/lib/labels'

const TIER_VARIANTS: Record<RiskTier, ComponentProps<typeof Badge>['variant']> = {
  low: 'success-light',
  medium: 'warning-light',
  high: 'destructive-outline',
  very_high: 'destructive',
}

export function TierBadge({ tier }: { tier: RiskTier }) {
  return <Badge variant={TIER_VARIANTS[tier]}>{RISK_TIER_LABELS[tier]}</Badge>
}
