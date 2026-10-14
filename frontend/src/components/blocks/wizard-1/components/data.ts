import type { Shop } from '@/api/gen'

export type OnboardingValues = {
  name: string
  shipping: string
  handling: string
  callCost: string
  start: string
  end: string
}

export const money = (value: string) => Math.max(0, Math.round(Number(value.replace(/\D/g, '')) || 0))

export function failedDeliveryCost(values: OnboardingValues) {
  // A refused parcel pays shipping both ways plus handling.
  return money(values.shipping) * 2 + money(values.handling)
}

export function initialOnboardingValues(shop: Shop): OnboardingValues {
  const failed = shop.settings.failed_delivery_cost_vnd ?? 60_000
  return {
    name: shop.name,
    shipping: String(Math.round((failed * 0.4) / 1000) * 1000),
    handling: String(failed - Math.round((failed * 0.4) / 1000) * 1000 * 2),
    callCost: String(shop.settings.ai_call_cost_vnd ?? 1_500),
    start: shop.settings.contact_hours?.start ?? '08:00',
    end: shop.settings.contact_hours?.end ?? '21:00',
  }
}
