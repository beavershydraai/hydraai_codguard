import type { LinkProps } from '@tanstack/react-router'
import { ChartLineIcon, ClipboardCheckIcon, HouseIcon, PackageIcon, SettingsIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import type { RiskTier } from '@/api/gen'
import { RISK_TIER_LABELS } from '@/lib/labels'

// ── Types ──

export type NavItem = {
  id: string
  label: string
  icon: ReactNode
  to: LinkProps['to']
  /** Match only the exact path (for the index route). */
  exact?: boolean
}

export type TierShortcut = {
  tier: RiskTier
  name: string
  color: string
}

// ── Nav Main ──

export const NAV_MAIN: NavItem[] = [
  { id: 'overview', label: 'Tổng quan', icon: <HouseIcon />, to: '/', exact: true },
  { id: 'orders', label: 'Đơn hàng', icon: <PackageIcon />, to: '/orders' },
  { id: 'review', label: 'Chờ duyệt', icon: <ClipboardCheckIcon />, to: '/review' },
  { id: 'backtest', label: 'Backtest', icon: <ChartLineIcon />, to: '/backtest' },
]

// ── Tier shortcuts (the block's "Resources" group) ──

export const TIER_SHORTCUTS: TierShortcut[] = [
  { tier: 'very_high', name: RISK_TIER_LABELS.very_high, color: 'bg-red-500' },
  { tier: 'high', name: RISK_TIER_LABELS.high, color: 'bg-orange-500' },
  { tier: 'medium', name: RISK_TIER_LABELS.medium, color: 'bg-amber-500' },
  { tier: 'low', name: RISK_TIER_LABELS.low, color: 'bg-emerald-500' },
]

// ── Nav Secondary ──

export const NAV_SECONDARY: NavItem[] = [
  { id: 'settings', label: 'Cài đặt', icon: <SettingsIcon />, to: '/settings' },
]
