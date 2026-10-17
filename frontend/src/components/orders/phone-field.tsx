import type { Country } from 'react-phone-number-input'

import { PhoneInput } from '@/components/reui/phone-input'

/** The countries the demo shop has branches in (backend/config/branches.yaml). */
const COUNTRIES: Country[] = ['VN', 'SG', 'PH']

/**
 * The buyer's phone with a country picker: ReUI phone input, limited to the shop's countries. It
 * gives the number in international form (`+84…`). Nothing here rejects a number: an invalid
 * phone is held for review by the decision engine, not refused at entry.
 */
export function PhoneField({
  id,
  value,
  onChange,
  required,
}: {
  id: string
  value: string
  onChange: (value: string) => void
  required?: boolean
}) {
  return (
    <PhoneInput
      id={id}
      countries={COUNTRIES}
      defaultCountry="VN"
      value={value}
      onChange={(next) => onChange(next ?? '')}
      placeholder="Phone number"
      required={required}
    />
  )
}
