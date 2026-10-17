import { TimePicker, TimePickerContent, TimePickerInput } from '@/components/reui/time-picker'

/**
 * A time of day as `HH:mm` in 24-hour time, on 5-minute steps: ReUI time picker (c-time-picker-3),
 * typed or picked. `onChange` takes the same shape as an input's change event, so it drops in
 * where `<Input type="time">` was.
 */
export function TimeField({
  id,
  value,
  onChange,
  min = '08:00',
  max = '21:00',
  'aria-label': ariaLabel,
}: {
  id?: string
  value: string
  onChange: (event: { target: { value: string } }) => void
  min?: string
  max?: string
  'aria-label'?: string
}) {
  return (
    <TimePicker
      id={id}
      hourCycle={24}
      minuteStep={5}
      min={min}
      max={max}
      value={value || null}
      onValueChange={(next) => onChange({ target: { value: next ?? '' } })}
    >
      <TimePickerInput className="w-28" aria-label={ariaLabel} />
      <TimePickerContent align="end" />
    </TimePicker>
  )
}
