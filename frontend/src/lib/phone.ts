import { parsePhoneNumber } from 'react-phone-number-input'

/**
 * A stored phone in the international form the field edits. A number already written with `+`
 * stays as it is (libphonenumber would drop a 0 after the calling code, and `+84000…` must keep
 * matching the same phone). A national number (`09…`) is read as Vietnamese; text that is no
 * phone number at all comes back empty.
 */
export function toInternational(phone: string): string {
  const compact = phone.replace(/[\s.()-]/g, '')
  if (/^\+\d+$/.test(compact)) return compact
  if (!compact) return ''
  try {
    return parsePhoneNumber(compact, 'VN')?.number ?? ''
  } catch {
    return ''
  }
}
