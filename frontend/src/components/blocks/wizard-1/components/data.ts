import type { CountrySettings, CountrySettingsUpdate, Shop } from '@/api/gen'
import { fromMinor, toMinor } from '@/lib/labels'

/** One country's costs as the owner types them (in the currency's main unit) and its hours. */
export type CountryValues = {
  country: CountrySettings['country']
  currency: CountrySettings['currency']
  failed: string
  callCost: string
  start: string
  end: string
}

export type OnboardingValues = {
  name: string
  countries: CountryValues[]
}

export function initialOnboardingValues(shop: Shop): OnboardingValues {
  return {
    name: shop.name,
    countries: shop.countries.map((c) => ({
      country: c.country,
      currency: c.currency,
      failed: fromMinor(c.failed_delivery_cost_vnd ?? 0, c.currency),
      callCost: fromMinor(c.ai_call_cost_vnd ?? 0, c.currency),
      start: c.contact_hours?.start ?? '08:00',
      end: c.contact_hours?.end ?? '21:00',
    })),
  }
}

/** The `countries` of the PATCH /shop body, amounts back in minor units. */
export function countryUpdates(values: OnboardingValues): CountrySettingsUpdate[] {
  return values.countries.map((c) => ({
    country: c.country,
    failed_delivery_cost_vnd: toMinor(c.failed, c.currency),
    ai_call_cost_vnd: toMinor(c.callCost, c.currency),
    contact_hours: { start: c.start, end: c.end },
  }))
}

export const hoursValid = (c: Pick<CountryValues, 'start' | 'end'>) =>
  c.start >= '08:00' && c.end <= '21:00' && c.start < c.end
