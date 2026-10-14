import { ArrowLeftIcon, ArrowRightIcon, CheckIcon, LoaderCircleIcon } from 'lucide-react'
import { type FormEvent, useState } from 'react'

import type { Policy, Shop } from '@/api/gen'
import { Badge } from '@/components/reui/badge'
import {
  Stepper,
  StepperContent,
  StepperIndicator,
  StepperItem,
  StepperNav,
  StepperPanel,
  StepperSeparator,
  StepperTitle,
  StepperTrigger,
} from '@/components/reui/stepper'
import { TierBadge } from '@/components/tier-badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { InputGroup, InputGroupAddon, InputGroupInput, InputGroupText } from '@/components/ui/input-group'
import { Separator } from '@/components/ui/separator'
import { DECISION_ACTION_LABELS, formatVnd } from '@/lib/labels'

import { failedDeliveryCost, initialOnboardingValues, money, type OnboardingValues } from './data'

// Shop onboarding (E7.1) in the three-step grammar of ReUI wizard-1: horizontal stepper,
// per-step validation, and a review step. Every value starts at a sensible default, so the
// shop can finish without changing anything.

const STEPS = [
  { id: 'shop', step: 1, title: 'Shop' },
  { id: 'costs', step: 2, title: 'Chi phí & giờ liên hệ' },
  { id: 'policy', step: 3, title: 'Policy & xác nhận' },
] as const

type Errors = Partial<Record<keyof OnboardingValues, string>>

function stepErrors(step: number, v: OnboardingValues): Errors {
  const errors: Errors = {}
  if (step === 1 && v.name.trim().length < 2) errors.name = 'Nhập tên shop (ít nhất 2 ký tự).'
  if (step === 2) {
    if (money(v.shipping) <= 0) errors.shipping = 'Nhập phí ship trung bình của một đơn.'
    if (!(v.start >= '08:00' && v.end <= '21:00' && v.start < v.end))
      errors.end = 'Giờ liên hệ phải nằm trong 08:00–21:00.'
  }
  return errors
}

export function OnboardingWizard({
  shop,
  policy,
  submitting,
  onComplete,
}: {
  shop: Shop
  policy: Policy
  submitting: boolean
  onComplete: (values: OnboardingValues) => void
}) {
  const [current, setCurrent] = useState(1)
  const [unlocked, setUnlocked] = useState(1)
  const [values, setValues] = useState(() => initialOnboardingValues(shop))
  const [errors, setErrors] = useState<Errors>({})

  const set = (key: keyof OnboardingValues) => (event: { target: { value: string } }) => {
    setValues((v) => ({ ...v, [key]: event.target.value }))
    setErrors((e) => ({ ...e, [key]: undefined }))
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const found = stepErrors(current, values)
    if (Object.values(found).some(Boolean)) {
      setErrors(found)
      return
    }
    if (current < STEPS.length) {
      setUnlocked((u) => Math.max(u, current + 1))
      setCurrent(current + 1)
      return
    }
    onComplete(values)
  }

  const isLast = current === STEPS.length

  return (
    <form onSubmit={handleSubmit} className="flex w-full max-w-xl flex-col" aria-label="Thiết lập shop">
      <Card>
        <Stepper
          value={current}
          onValueChange={(next) => next <= unlocked && setCurrent(next)}
          indicators={{
            completed: <CheckIcon className="size-3.5" />,
            loading: <LoaderCircleIcon className="size-3.5 animate-spin" />,
          }}
          className="w-full space-y-3"
        >
          <CardHeader className="flex items-center py-1">
            <StepperNav aria-label="Các bước thiết lập" className="items-center">
              {STEPS.map((step, index) => (
                <StepperItem
                  key={step.id}
                  step={step.step}
                  disabled={step.step > unlocked}
                  loading={submitting && step.step === current}
                  className="relative"
                >
                  <StepperTrigger className="flex justify-start gap-1.5">
                    <StepperIndicator className="relative isolate size-6 overflow-visible rounded-full before:pointer-events-none before:absolute before:inset-0 before:z-10 before:rounded-full before:border before:border-dashed before:border-transparent before:content-[''] data-[state=active]:border-0 data-[state=active]:bg-primary/10 data-[state=active]:text-primary data-[state=active]:before:animate-[spin_8s_linear_infinite] data-[state=active]:before:border-primary data-[state=completed]:bg-primary data-[state=inactive]:border-border data-[state=inactive]:bg-muted data-[state=inactive]:text-foreground motion-reduce:data-[state=active]:before:animate-none">
                      {index + 1}
                    </StepperIndicator>
                    <StepperTitle className="text-sm group-data-[state=inactive]/step:text-foreground">
                      {step.title}
                    </StepperTitle>
                  </StepperTrigger>
                  {index + 1 < STEPS.length && (
                    <StepperSeparator className="bg-border group-data-[state=completed]/step:bg-primary md:mx-2.5" />
                  )}
                </StepperItem>
              ))}
            </StepperNav>
          </CardHeader>
          <Separator />
          <CardContent>
            <StepperPanel className="text-sm">
              <StepperContent value={1}>
                <FieldGroup className="gap-4">
                  <Field data-invalid={!!errors.name}>
                    <FieldLabel htmlFor="onb-name">Tên shop</FieldLabel>
                    <Input
                      id="onb-name"
                      value={values.name}
                      onChange={set('name')}
                      aria-invalid={!!errors.name}
                      autoFocus
                    />
                    <FieldDescription>
                      AI tự giới thiệu là trợ lý của shop này khi gọi khách.
                    </FieldDescription>
                    {errors.name && <FieldError>{errors.name}</FieldError>}
                  </Field>
                  <p className="rounded-lg bg-muted/60 p-3 text-xs text-muted-foreground">
                    Đơn mới vào bằng file CSV, công cụ bán hàng (API key{' '}
                    {shop.intake_api_key_last4 ? `••••${shop.intake_api_key_last4}` : 'tạo sau'}) hoặc tạo
                    tay. Mỗi đơn được chấm điểm rủi ro ngay khi vào.
                  </p>
                </FieldGroup>
              </StepperContent>

              <StepperContent value={2}>
                <FieldGroup className="gap-4">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field data-invalid={!!errors.shipping}>
                      <FieldLabel htmlFor="onb-ship">Phí ship trung bình một chiều</FieldLabel>
                      <Money id="onb-ship" value={values.shipping} onChange={set('shipping')} />
                      {errors.shipping && <FieldError>{errors.shipping}</FieldError>}
                    </Field>
                    <Field>
                      <FieldLabel htmlFor="onb-handling">Chi phí xử lý hàng hoàn</FieldLabel>
                      <Money id="onb-handling" value={values.handling} onChange={set('handling')} />
                    </Field>
                  </div>
                  <p className="text-sm">
                    Một lần giao thất bại tốn khoảng{' '}
                    <span className="font-semibold tabular-nums">
                      {formatVnd(failedDeliveryCost(values))}
                    </span>{' '}
                    <Badge variant="info-light" size="sm">
                      ước tính
                    </Badge>
                  </p>
                  <Field>
                    <FieldLabel htmlFor="onb-call">Chi phí một cuộc gọi AI</FieldLabel>
                    <Money id="onb-call" value={values.callCost} onChange={set('callCost')} />
                    <FieldDescription>
                      Chỉ gọi khi thiệt hại dự kiến của đơn lớn hơn chi phí này.
                    </FieldDescription>
                  </Field>
                  <Field data-invalid={!!errors.end}>
                    <FieldLabel htmlFor="onb-start">Giờ được liên hệ khách</FieldLabel>
                    <div className="flex items-center gap-2">
                      <Input
                        id="onb-start"
                        type="time"
                        value={values.start}
                        onChange={set('start')}
                        min="08:00"
                        max="21:00"
                      />
                      <span className="text-muted-foreground">–</span>
                      <Input
                        aria-label="Đến"
                        type="time"
                        value={values.end}
                        onChange={set('end')}
                        min="08:00"
                        max="21:00"
                      />
                    </div>
                    {errors.end && <FieldError>{errors.end}</FieldError>}
                  </Field>
                </FieldGroup>
              </StepperContent>

              <StepperContent value={3}>
                <div className="flex flex-col gap-4">
                  <p className="text-muted-foreground">
                    Policy mặc định dưới đây dùng được ngay; đổi lúc nào cũng được trong Cài đặt.
                  </p>
                  <ul className="flex flex-col divide-y rounded-lg border">
                    {policy.tiers.map((t) => (
                      <li
                        key={t.tier}
                        className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5"
                      >
                        <TierBadge tier={t.tier} />
                        <span className="text-right">
                          {DECISION_ACTION_LABELS[t.action]}
                          {t.if_no_response && (
                            <span className="block text-xs text-muted-foreground">
                              Không phản hồi sau {t.no_response_after_minutes} phút →{' '}
                              {DECISION_ACTION_LABELS[t.if_no_response]}
                            </span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                  <dl className="grid grid-cols-2 gap-3 rounded-lg bg-muted/60 p-3 text-xs">
                    <div>
                      <dt className="text-muted-foreground">Shop</dt>
                      <dd className="font-medium">{values.name}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Giao thất bại</dt>
                      <dd className="font-medium tabular-nums">{formatVnd(failedDeliveryCost(values))}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Cuộc gọi AI</dt>
                      <dd className="font-medium tabular-nums">{formatVnd(money(values.callCost))}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Giờ liên hệ</dt>
                      <dd className="font-medium tabular-nums">
                        {values.start}–{values.end}
                      </dd>
                    </div>
                  </dl>
                </div>
              </StepperContent>
            </StepperPanel>
          </CardContent>
          <CardFooter className="flex justify-end gap-2">
            {current > 1 && (
              <Button type="button" variant="outline" onClick={() => setCurrent((c) => Math.max(1, c - 1))}>
                <ArrowLeftIcon data-icon="inline-start" aria-hidden="true" />
                Quay lại
              </Button>
            )}
            <Button type="submit" disabled={submitting}>
              {isLast ? 'Bắt đầu dùng COD Guard' : 'Tiếp tục'}
              {!isLast && <ArrowRightIcon data-icon="inline-end" aria-hidden="true" />}
            </Button>
          </CardFooter>
        </Stepper>
      </Card>
    </form>
  )
}

function Money({
  id,
  value,
  onChange,
}: {
  id: string
  value: string
  onChange: (e: { target: { value: string } }) => void
}) {
  return (
    <InputGroup>
      <InputGroupInput
        id={id}
        value={value}
        onChange={onChange}
        inputMode="numeric"
        className="text-right tabular-nums"
      />
      <InputGroupAddon align="inline-end">
        <InputGroupText>₫</InputGroupText>
      </InputGroupAddon>
    </InputGroup>
  )
}
