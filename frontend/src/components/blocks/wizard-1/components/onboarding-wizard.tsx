import { ArrowLeftIcon, ArrowRightIcon, CheckIcon, LoaderCircleIcon } from 'lucide-react'
import { type FormEvent, useCallback, useState } from 'react'

import type { HistoryImportResult, Policy, Shop } from '@/api/gen'
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
import { TimeField } from '@/components/time-field'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { InputGroup, InputGroupAddon, InputGroupInput, InputGroupText } from '@/components/ui/input-group'
import { Separator } from '@/components/ui/separator'
import { COUNTRY_LABELS, CURRENCY_SYMBOLS, DECISION_ACTION_LABELS, formatMoney, toMinor } from '@/lib/labels'

import { type CountryValues, hoursValid, initialOnboardingValues, type OnboardingValues } from './data'
import { HistoryStep, TrainStep } from './history-steps'

// Shop onboarding (E7.1) in the grammar of ReUI wizard-1: horizontal stepper, per-step
// validation, and a review step. Every value starts at the default of its country (one set of
// costs and contact hours per country where the shop has branches), so the shop can finish
// without changing anything. A new shop then uploads its past orders and its risk models learn
// from them (history-steps.tsx); both steps can be skipped.

const STEPS = [
  { id: 'shop', step: 1, title: 'Shop' },
  { id: 'costs', step: 2, title: 'Costs' },
  { id: 'history', step: 3, title: 'History' },
  { id: 'model', step: 4, title: 'Risk model' },
  { id: 'policy', step: 5, title: 'Review' },
] as const

/** Field errors by key: `name`, or `<country>.failed` / `<country>.hours`. */
type Errors = Record<string, string | undefined>

function stepErrors(step: number, v: OnboardingValues): Errors {
  const errors: Errors = {}
  if (step === 1 && v.name.trim().length < 2) errors.name = 'Enter the shop name (at least 2 characters).'
  if (step === 2) {
    for (const c of v.countries) {
      if (toMinor(c.failed, c.currency) <= 0)
        errors[`${c.country}.failed`] = 'Enter the cost of a failed delivery.'
      if (!hoursValid(c)) errors[`${c.country}.hours`] = 'Contact hours must be within 08:00–21:00.'
    }
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
  // History: undefined until uploaded or skipped; null when skipped. Training is skipped with it.
  const [history, setHistory] = useState<HistoryImportResult | null | undefined>(undefined)
  const [trained, setTrained] = useState(false)
  const onTrained = useCallback(() => {
    setTrained(true)
    setErrors((e) => ({ ...e, model: undefined }))
  }, [])

  const setName = (event: { target: { value: string } }) => {
    setValues((v) => ({ ...v, name: event.target.value }))
    setErrors((e) => ({ ...e, name: undefined }))
  }
  const setCountry =
    (country: CountryValues['country'], key: keyof CountryValues, error: string) =>
    (event: { target: { value: string } }) => {
      setValues((v) => ({
        ...v,
        countries: v.countries.map((c) => (c.country === country ? { ...c, [key]: event.target.value } : c)),
      }))
      setErrors((e) => ({ ...e, [`${country}.${error}`]: undefined }))
    }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const found = stepErrors(current, values)
    if (current === 3 && history === undefined) found.history = 'Upload your past orders, or skip this step.'
    if (current === 4 && history && !trained) found.model = 'Wait until your risk model has learned.'
    if (Object.values(found).some(Boolean)) {
      setErrors(found)
      return
    }
    if (current === 3 && history === null) {
      // No history: nothing to learn from yet, go straight to the review.
      setUnlocked((u) => Math.max(u, 5))
      setCurrent(5)
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
    <form onSubmit={handleSubmit} className="flex w-full max-w-2xl flex-col" aria-label="Shop setup">
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
            <StepperNav aria-label="Setup steps" className="items-center">
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
                    <FieldLabel htmlFor="onb-name">Shop name</FieldLabel>
                    <Input
                      id="onb-name"
                      value={values.name}
                      onChange={setName}
                      aria-invalid={!!errors.name}
                      autoFocus
                    />
                    <FieldDescription>
                      The AI introduces itself as this shop's assistant when it calls buyers.
                    </FieldDescription>
                    {errors.name && <FieldError>{errors.name}</FieldError>}
                  </Field>
                  <p className="rounded-lg bg-muted/60 p-3 text-xs text-muted-foreground">
                    New orders come in by CSV file, from a sales tool (API key{' '}
                    {shop.intake_api_key_last4 ? `••••${shop.intake_api_key_last4}` : 'created later'}) or by
                    hand. Each order gets a risk score as soon as it arrives.
                  </p>
                </FieldGroup>
              </StepperContent>

              <StepperContent value={2}>
                <FieldGroup className="gap-5">
                  <p className="text-muted-foreground">
                    One set per country where the shop has branches, in that country's currency and local
                    time. Calls and links are used only when an order's expected loss is higher than their
                    cost.
                  </p>
                  {values.countries.map((c) => {
                    const id = `onb-${c.country}`
                    return (
                      <fieldset key={c.country} className="flex flex-col gap-3 rounded-lg border p-3">
                        <legend className="px-1 text-sm font-medium">
                          {COUNTRY_LABELS[c.country] ?? c.country}{' '}
                          <Badge variant="outline" size="sm">
                            {c.currency}
                          </Badge>
                        </legend>
                        <div className="grid gap-3 sm:grid-cols-2">
                          <Field data-invalid={!!errors[`${c.country}.failed`]}>
                            <FieldLabel htmlFor={`${id}-failed`}>Cost of one failed delivery</FieldLabel>
                            <Money
                              id={`${id}-failed`}
                              currency={c.currency}
                              value={c.failed}
                              onChange={setCountry(c.country, 'failed', 'failed')}
                            />
                            <FieldDescription>Shipping both ways plus handling.</FieldDescription>
                            {errors[`${c.country}.failed`] && (
                              <FieldError>{errors[`${c.country}.failed`]}</FieldError>
                            )}
                          </Field>
                          <Field>
                            <FieldLabel htmlFor={`${id}-call`}>Cost of one AI call</FieldLabel>
                            <Money
                              id={`${id}-call`}
                              currency={c.currency}
                              value={c.callCost}
                              onChange={setCountry(c.country, 'callCost', 'call')}
                            />
                          </Field>
                        </div>
                        <Field data-invalid={!!errors[`${c.country}.hours`]}>
                          <FieldLabel htmlFor={`${id}-start`}>Hours when buyers may be contacted</FieldLabel>
                          <div className="flex items-center gap-2">
                            <TimeField
                              id={`${id}-start`}
                              value={c.start}
                              onChange={setCountry(c.country, 'start', 'hours')}
                            />
                            <span className="text-muted-foreground">–</span>
                            <TimeField
                              aria-label={`Until, ${COUNTRY_LABELS[c.country] ?? c.country}`}
                              value={c.end}
                              onChange={setCountry(c.country, 'end', 'hours')}
                            />
                          </div>
                          {errors[`${c.country}.hours`] && (
                            <FieldError>{errors[`${c.country}.hours`]}</FieldError>
                          )}
                        </Field>
                      </fieldset>
                    )
                  })}
                </FieldGroup>
              </StepperContent>

              <StepperContent value={3}>
                <HistoryStep
                  onDone={(result) => {
                    setHistory(result)
                    setErrors((e) => ({ ...e, history: undefined }))
                  }}
                />
                {errors.history && <FieldError className="mt-3">{errors.history}</FieldError>}
              </StepperContent>

              <StepperContent value={4}>
                <TrainStep onDone={onTrained} />
                {errors.model && <FieldError className="mt-3">{errors.model}</FieldError>}
              </StepperContent>

              <StepperContent value={5}>
                <div className="flex flex-col gap-4">
                  <p className="text-muted-foreground">
                    The default policy below works out of the box; change it any time in Settings.
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
                              No response after {t.no_response_after_minutes} min →{' '}
                              {DECISION_ACTION_LABELS[t.if_no_response]}
                            </span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                  <div className="flex flex-col gap-2 rounded-lg bg-muted/60 p-3 text-xs">
                    <p>
                      <span className="text-muted-foreground">Shop: </span>
                      <span className="font-medium">{values.name}</span>
                    </p>
                    <dl className="grid grid-cols-[auto_1fr_1fr_auto] gap-x-3 gap-y-1">
                      <dt className="text-muted-foreground">Country</dt>
                      <dt className="text-muted-foreground">Failed delivery</dt>
                      <dt className="text-muted-foreground">AI call</dt>
                      <dt className="text-muted-foreground">Contact hours</dt>
                      {values.countries.map((c) => (
                        <div key={c.country} className="contents">
                          <dd className="font-medium">{c.country}</dd>
                          <dd className="tabular-nums">
                            {formatMoney(toMinor(c.failed, c.currency), c.currency)}
                          </dd>
                          <dd className="tabular-nums">
                            {formatMoney(toMinor(c.callCost, c.currency), c.currency)}
                          </dd>
                          <dd className="tabular-nums">
                            {c.start}–{c.end}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                </div>
              </StepperContent>
            </StepperPanel>
          </CardContent>
          <CardFooter className="flex justify-end gap-2">
            {current > 1 && (
              <Button type="button" variant="outline" onClick={() => setCurrent((c) => Math.max(1, c - 1))}>
                <ArrowLeftIcon data-icon="inline-start" aria-hidden="true" />
                Back
              </Button>
            )}
            <Button type="submit" disabled={submitting}>
              {isLast ? 'Start using COD Guard' : 'Continue'}
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
  currency,
  value,
  onChange,
}: {
  id: string
  currency: string
  value: string
  onChange: (e: { target: { value: string } }) => void
}) {
  return (
    <InputGroup>
      <InputGroupInput
        id={id}
        value={value}
        onChange={onChange}
        inputMode={currency === 'VND' ? 'numeric' : 'decimal'}
        className="text-right tabular-nums"
      />
      <InputGroupAddon align="inline-end">
        <InputGroupText>{CURRENCY_SYMBOLS[currency] ?? currency}</InputGroupText>
      </InputGroupAddon>
    </InputGroup>
  )
}
