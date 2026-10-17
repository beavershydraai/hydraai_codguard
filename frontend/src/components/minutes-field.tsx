import {
  NumberField,
  NumberFieldDecrement,
  NumberFieldGroup,
  NumberFieldIncrement,
  NumberFieldInput,
} from '@/components/reui/number-field'

const MINUTES: Intl.NumberFormatOptions = { style: 'unit', unit: 'minute', unitDisplay: 'short' }

/** A number of minutes with − and + buttons, kept between `min` and `max`: ReUI number field. */
export function MinutesField({
  value,
  onChange,
  min,
  max,
  step = 5,
  className,
  'aria-label': ariaLabel,
}: {
  value: number | null
  onChange: (value: number | null) => void
  min: number
  max: number
  step?: number
  className?: string
  'aria-label': string
}) {
  return (
    <NumberField
      value={value}
      onValueChange={onChange}
      min={min}
      max={max}
      step={step}
      format={MINUTES}
      className={className}
    >
      <NumberFieldGroup>
        <NumberFieldDecrement />
        <NumberFieldInput aria-label={ariaLabel} />
        <NumberFieldIncrement />
      </NumberFieldGroup>
    </NumberField>
  )
}
