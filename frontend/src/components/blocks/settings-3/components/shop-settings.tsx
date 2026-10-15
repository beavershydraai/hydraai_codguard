import { useMutation, useQueryClient } from '@tanstack/react-query'
import { InfoIcon, LockIcon } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import type {
  CallAutomation,
  CallAutomationMode,
  DecisionAction,
  Policy,
  RiskTier,
  SalesChannel,
  Shop,
  TierPolicy,
  Weekday,
} from '@/api/gen'
import { updatePolicyMutation, updateShopMutation } from '@/api/gen/@tanstack/react-query.gen'
import { Badge } from '@/components/reui/badge'
import {
  Frame,
  FrameDescription,
  FrameFooter,
  FrameHeader,
  FramePanel,
  FrameTitle,
} from '@/components/ui/frame'
import {
  Timeline,
  TimelineContent,
  TimelineIndicator,
  TimelineItem,
  TimelineSeparator,
} from '@/components/reui/timeline'
import { TierBadge } from '@/components/tier-badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { FieldGroup } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { InputGroup, InputGroupAddon, InputGroupInput, InputGroupText } from '@/components/ui/input-group'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { invalidate, problemMessage } from '@/lib/api'
import {
  CALL_AUTOMATION_MODE_LABELS,
  COUNTRY_LABELS,
  CURRENCY_SYMBOLS,
  DECISION_ACTION_LABELS,
  formatDateTime,
  fromMinor,
  RISK_TIER_LABELS,
  SALES_CHANNEL_LABELS,
  toMinor,
  WEEKDAY_LABELS,
} from '@/lib/labels'

import { SettingField } from './setting-field'

// Shop settings per country (E7.1), tier policy and call automation (E7.6) and their change
// history (E4.6), in the setting-row grammar of ReUI settings-3 inside tabs like settings-7. Staff
// can read but not change policy or costs (E7.7); the backend enforces it too (403).

export type SettingsTab = 'shop' | 'policy' | 'automation' | 'history'

export function ShopSettingsView({
  shop,
  policy,
  versions,
  canEdit,
  tab,
  onTabChange,
}: {
  shop: Shop
  policy: Policy
  versions: Policy[]
  canEdit: boolean
  tab: SettingsTab
  onTabChange: (tab: SettingsTab) => void
}) {
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Costs and policy decide when COD Guard contacts the buyer.
        </p>
      </div>

      {!canEdit && (
        <Alert>
          <LockIcon />
          <AlertTitle>View only</AlertTitle>
          <AlertDescription>
            Staff accounts cannot change costs or policy. Ask the shop owner.
          </AlertDescription>
        </Alert>
      )}

      <Tabs value={tab} onValueChange={(value) => onTabChange(value as SettingsTab)} className="gap-4">
        <TabsList>
          <TabsTrigger value="shop">Shop &amp; costs</TabsTrigger>
          <TabsTrigger value="policy">Policy by risk tier</TabsTrigger>
          <TabsTrigger value="automation">Call automation</TabsTrigger>
          <TabsTrigger value="history">Change history</TabsTrigger>
        </TabsList>
        <TabsContent value="shop">
          <ShopForm shop={shop} canEdit={canEdit} />
        </TabsContent>
        <TabsContent value="policy">
          <PolicyForm policy={policy} canEdit={canEdit} />
        </TabsContent>
        <TabsContent value="automation">
          <AutomationForm policy={policy} canEdit={canEdit} />
        </TabsContent>
        <TabsContent value="history">
          <PolicyHistory versions={versions} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

// ── Shop and costs ──

type CountryForm = {
  failed: string
  call: string
  link: string
  deposit: string
  start: string
  end: string
}

function ShopForm({ shop, canEdit }: { shop: Shop; canEdit: boolean }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState(shop.name)
  const [country, setCountry] = useState<string>(shop.countries[0]?.country ?? 'VN')
  const [forms, setForms] = useState<Record<string, CountryForm>>(() =>
    Object.fromEntries(
      shop.countries.map((c) => [
        c.country,
        {
          failed: fromMinor(c.failed_delivery_cost_vnd ?? 0, c.currency),
          call: fromMinor(c.ai_call_cost_vnd ?? 0, c.currency),
          link: fromMinor(c.confirmation_link_cost_vnd ?? 0, c.currency),
          deposit: fromMinor(c.deposit_request_cost_vnd ?? 0, c.currency),
          start: c.contact_hours?.start ?? '08:00',
          end: c.contact_hours?.end ?? '21:00',
        },
      ]),
    ),
  )
  const mutation = useMutation({
    ...updateShopMutation(),
    onSuccess: () => {
      toast.success('Shop settings saved')
      void invalidate(queryClient, 'getShop', 'getDashboardSummary')
    },
    onError: (error) => toast.error('Could not save', { description: problemMessage(error) }),
  })
  const current = shop.countries.find((c) => c.country === country) ?? shop.countries[0]!
  const form = forms[current.country]!
  const set = (key: keyof CountryForm) => (event: { target: { value: string } }) =>
    setForms((f) => ({ ...f, [current.country]: { ...f[current.country]!, [key]: event.target.value } }))
  const badHours = shop.countries.filter((c) => !hoursValid(forms[c.country]!))
  const money = (id: string, key: keyof CountryForm) => (
    <MoneyInput id={id} currency={current.currency} value={form[key]} onChange={set(key)} />
  )

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        mutation.mutate({
          body: {
            name: name.trim(),
            countries: shop.countries.map((c) => {
              const f = forms[c.country]!
              return {
                country: c.country,
                failed_delivery_cost_vnd: toMinor(f.failed, c.currency),
                ai_call_cost_vnd: toMinor(f.call, c.currency),
                confirmation_link_cost_vnd: toMinor(f.link, c.currency),
                deposit_request_cost_vnd: toMinor(f.deposit, c.currency),
                contact_hours: { start: f.start, end: f.end },
              }
            }),
          },
        })
      }}
    >
      <Frame className="w-full">
        <FrameHeader className="px-2! py-2.5!">
          <FrameTitle>Shop &amp; costs</FrameTitle>
          <FrameDescription>
            The defaults work out of the box; adjust them to the shop's real delivery costs. Each country
            where the shop has branches has its own costs, in its currency, and contact hours, in its local
            time.
          </FrameDescription>
        </FrameHeader>
        <FramePanel className="p-0">
          <fieldset disabled={!canEdit}>
            <FieldGroup className="gap-0">
              <SettingField
                title="Shop name"
                description="The name used in AI calls and confirmation messages."
                labelFor="shop-name"
              >
                <Input
                  id="shop-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  required
                  maxLength={100}
                />
              </SettingField>
              <SettingField
                title="Country"
                description="Costs and contact hours below apply to this country."
              >
                <Tabs value={current.country} onValueChange={setCountry}>
                  <TabsList>
                    {shop.countries.map((c) => (
                      <TabsTrigger key={c.country} value={c.country}>
                        {COUNTRY_LABELS[c.country] ?? c.country} · {c.currency}
                      </TabsTrigger>
                    ))}
                  </TabsList>
                </Tabs>
              </SettingField>
              <SettingField
                title="Cost of one failed delivery"
                description="Shipping both ways plus handling. Used to work out each order's expected loss."
                badge={{ label: 'Important', variant: 'destructive-light' }}
                labelFor="cost-failed"
              >
                {money('cost-failed', 'failed')}
              </SettingField>
              <SettingField
                title="Cost of one AI call"
                description="Calls are placed only when the expected loss is higher than this cost."
                labelFor="cost-call"
              >
                {money('cost-call', 'call')}
              </SettingField>
              <SettingField
                title="Cost of sending a confirmation link"
                description="Zalo ZNS / SMS message."
                labelFor="cost-link"
              >
                {money('cost-link', 'link')}
              </SettingField>
              <SettingField
                title="Cost of requiring a deposit"
                description="Estimated revenue lost when buyers abandon an order because of the deposit."
                labelFor="cost-deposit"
              >
                {money('cost-deposit', 'deposit')}
              </SettingField>
              <SettingField
                title="Contact hours"
                description="Local time of the country. No contact outside 08:00–21:00."
                last
                contentClassName="@md/field-group:w-78"
              >
                <div className="flex items-center gap-2">
                  <Input
                    type="time"
                    aria-label="Start"
                    value={form.start}
                    onChange={set('start')}
                    min="08:00"
                    max="21:00"
                  />
                  <span className="text-muted-foreground">–</span>
                  <Input
                    type="time"
                    aria-label="End"
                    value={form.end}
                    onChange={set('end')}
                    min="08:00"
                    max="21:00"
                  />
                </div>
              </SettingField>
            </FieldGroup>
          </fieldset>
        </FramePanel>
        <FrameFooter className="flex-row items-center justify-between gap-3 px-2! py-2.5!">
          <span className="text-xs text-muted-foreground">
            {badHours.length > 0 ? (
              <span className="text-destructive">
                Contact hours must be within 08:00–21:00 ({badHours.map((c) => c.country).join(', ')}).
              </span>
            ) : (
              <>
                Order intake API key:{' '}
                {shop.intake_api_key_last4 ? `••••${shop.intake_api_key_last4}` : 'not created'}
              </>
            )}
          </span>
          <Button type="submit" disabled={!canEdit || badHours.length > 0 || mutation.isPending}>
            {mutation.isPending && <Spinner data-icon="inline-start" />}
            Save changes
          </Button>
        </FrameFooter>
      </Frame>
    </form>
  )
}

const hoursValid = (f: Pick<CountryForm, 'start' | 'end'>) =>
  f.start >= '08:00' && f.end <= '21:00' && f.start < f.end

function MoneyInput({
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

// ── Tier policy ──

const ACTIONS: DecisionAction[] = [
  'ship_now',
  'send_confirmation_link',
  'ai_call',
  'require_deposit',
  'hold_for_review',
]
// Only the buyer or the shop cancels an order, so no escalation cancels (the backend rejects it).
const ESCALATIONS: DecisionAction[] = ['ai_call', 'hold_for_review']

function PolicyForm({ policy, canEdit }: { policy: Policy; canEdit: boolean }) {
  const queryClient = useQueryClient()
  const [tiers, setTiers] = useState<TierPolicy[]>(() => policy.tiers.map((t) => ({ ...t })))
  const mutation = useMutation({
    ...updatePolicyMutation(),
    onSuccess: (next) => {
      toast.success(`Policy version ${next.version} saved`, {
        description: 'Applies only to decisions made from now on.',
      })
      void invalidate(queryClient, 'getPolicy', 'listPolicyVersions')
    },
    onError: (error) => toast.error('Could not save', { description: problemMessage(error) }),
  })
  const update = (tier: RiskTier, patch: Partial<TierPolicy>) =>
    setTiers((current) => current.map((t) => (t.tier === tier ? { ...t, ...patch } : t)))
  const changed = JSON.stringify(tiers) !== JSON.stringify(policy.tiers)

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        mutation.mutate({ body: { tiers: tiers as Policy['tiers'] } })
      }}
    >
      <Frame className="w-full">
        <FrameHeader className="px-2! py-2.5!">
          <FrameTitle className="flex flex-wrap items-center gap-2">
            Policy by risk tier
            <Badge variant="outline" size="sm">
              Version {policy.version}
            </Badge>
          </FrameTitle>
          <FrameDescription>
            In effect since {formatDateTime(policy.effective_from)}. Buyers are contacted only when the
            expected loss is higher than the contact cost (costs per country in Shop &amp; costs).
          </FrameDescription>
        </FrameHeader>
        <FramePanel className="p-0">
          <fieldset disabled={!canEdit}>
            <FieldGroup className="gap-0">
              {tiers.map((t, i) => (
                <SettingField
                  key={t.tier}
                  title={`${RISK_TIER_LABELS[t.tier]} risk`}
                  description={<TierBadge tier={t.tier} />}
                  last={i === tiers.length - 1}
                  contentClassName="@md/field-group:w-[26rem]"
                >
                  <div className="grid gap-2 sm:grid-cols-[1fr_1fr]">
                    <ActionSelect
                      label="Action"
                      value={t.action}
                      options={ACTIONS}
                      onChange={(next) => {
                        const action = next as DecisionAction
                        update(t.tier, {
                          action,
                          if_no_response: action === 'ship_now' ? null : t.if_no_response,
                          no_response_after_minutes:
                            action === 'ship_now' ? null : t.no_response_after_minutes,
                        })
                      }}
                    />
                    <ActionSelect
                      label="If no response"
                      value={t.if_no_response ?? 'none'}
                      options={ESCALATIONS}
                      allowNone
                      disabled={t.action === 'ship_now' || t.action === 'hold_for_review'}
                      onChange={(value) =>
                        update(t.tier, {
                          if_no_response: value === 'none' ? null : (value as DecisionAction),
                          no_response_after_minutes:
                            value === 'none' ? null : (t.no_response_after_minutes ?? 120),
                        })
                      }
                    />
                    {t.if_no_response && (
                      <InputGroup className="sm:col-span-2">
                        <InputGroupAddon align="inline-start">
                          <InputGroupText>After</InputGroupText>
                        </InputGroupAddon>
                        <InputGroupInput
                          aria-label={`Wait for a response, ${RISK_TIER_LABELS[t.tier].toLowerCase()} risk`}
                          type="number"
                          min={1}
                          max={2880}
                          value={t.no_response_after_minutes ?? ''}
                          onChange={(event) =>
                            update(t.tier, { no_response_after_minutes: Number(event.target.value) || null })
                          }
                        />
                        <InputGroupAddon align="inline-end">
                          <InputGroupText>min</InputGroupText>
                        </InputGroupAddon>
                      </InputGroup>
                    )}
                  </div>
                </SettingField>
              ))}
            </FieldGroup>
          </fieldset>
        </FramePanel>
        <FrameFooter className="flex-row items-center justify-between gap-3 px-2! py-2.5!">
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <InfoIcon className="size-3.5" aria-hidden="true" />
            Orders that already have a decision keep the old policy.
          </span>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="ghost"
              disabled={!changed}
              onClick={() => setTiers(policy.tiers.map((t) => ({ ...t })))}
            >
              Undo
            </Button>
            <Button type="submit" disabled={!canEdit || !changed || mutation.isPending}>
              {mutation.isPending && <Spinner data-icon="inline-start" />}
              Save new version
            </Button>
          </div>
        </FrameFooter>
      </Frame>
    </form>
  )
}

function ActionSelect({
  label,
  value,
  options,
  onChange,
  allowNone = false,
  disabled = false,
}: {
  label: string
  value: string
  options: DecisionAction[]
  onChange: (value: string) => void
  allowNone?: boolean
  disabled?: boolean
}) {
  return (
    <Select value={value} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger className="w-full" aria-label={label}>
        <SelectValue placeholder={label} />
      </SelectTrigger>
      <SelectContent>
        <SelectGroup>
          {allowNone && <SelectItem value="none">Do nothing more</SelectItem>}
          {options.map((action) => (
            <SelectItem key={action} value={action}>
              {DECISION_ACTION_LABELS[action]}
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  )
}

// ── Call automation ──

const DEFAULT_AUTOMATION: Required<CallAutomation> = {
  mode: 'auto',
  min_tier: null,
  cod_ranges: [],
  channels: null,
  call_window: null,
  max_attempts: 2,
  retry_after_minutes: 30,
}
const CURRENCIES = ['VND', 'SGD', 'PHP'] as const
const CHANNELS = Object.keys(SALES_CHANNEL_LABELS) as SalesChannel[]
const WEEKDAYS = Object.keys(WEEKDAY_LABELS) as Weekday[]
const AUTO_TIERS: RiskTier[] = ['medium', 'high', 'very_high']

function AutomationForm({ policy, canEdit }: { policy: Policy; canEdit: boolean }) {
  const queryClient = useQueryClient()
  const initial = { ...DEFAULT_AUTOMATION, ...policy.automation }
  const [auto, setAuto] = useState(initial)
  const [ranges, setRanges] = useState<Record<string, { min: string; max: string }>>(() =>
    Object.fromEntries(
      CURRENCIES.map((cur) => {
        const r = initial.cod_ranges.find((x) => x.currency === cur)
        return [
          cur,
          {
            min: r?.min_cod != null ? fromMinor(r.min_cod, cur) : '',
            max: r?.max_cod != null ? fromMinor(r.max_cod, cur) : '',
          },
        ]
      }),
    ),
  )
  const mutation = useMutation({
    ...updatePolicyMutation(),
    onSuccess: (next) => {
      toast.success(`Policy version ${next.version} saved`, {
        description: 'Call automation applies to decisions made from now on.',
      })
      void invalidate(queryClient, 'getPolicy', 'listPolicyVersions')
    },
    onError: (error) => toast.error('Could not save', { description: problemMessage(error) }),
  })
  const update = (patch: Partial<typeof auto>) => setAuto((a) => ({ ...a, ...patch }))
  const callWindow = auto.call_window
  const windowValid =
    !callWindow ||
    (hoursValid(callWindow as { start: string; end: string }) && (callWindow.days?.length ?? 0) > 0)
  const retryValid = auto.retry_after_minutes >= 30 && auto.retry_after_minutes <= 1440
  const codRanges = CURRENCIES.flatMap((cur) => {
    const r = ranges[cur]!
    if (!r.min && !r.max) return []
    return [
      {
        currency: cur,
        min_cod: r.min ? toMinor(r.min, cur) : null,
        max_cod: r.max ? toMinor(r.max, cur) : null,
      },
    ]
  })
  const rangesValid = codRanges.every((r) => r.min_cod == null || r.max_cod == null || r.min_cod <= r.max_cod)
  const valid = windowValid && retryValid && rangesValid

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        mutation.mutate({
          body: { tiers: policy.tiers, automation: { ...auto, cod_ranges: codRanges } },
        })
      }}
    >
      <Frame className="w-full">
        <FrameHeader className="px-2! py-2.5!">
          <FrameTitle className="flex flex-wrap items-center gap-2">
            Call automation
            <Badge variant="outline" size="sm">
              Version {policy.version}
            </Badge>
          </FrameTitle>
          <FrameDescription>
            The engine still scores every order and picks the action. An AI call outside these rules is not
            placed: the order waits in Review with the call suggested, and you confirm it with AI confirmation
            call on the order page. Contact hours and the one-call-per-phone-per-day limit always apply.
          </FrameDescription>
        </FrameHeader>
        <FramePanel className="p-0">
          <fieldset disabled={!canEdit}>
            <FieldGroup className="gap-0">
              <SettingField title="Who starts AI calls" description="Suggest: every call waits for you.">
                <Select
                  value={auto.mode}
                  onValueChange={(mode) => update({ mode: mode as CallAutomationMode })}
                >
                  <SelectTrigger className="w-full" aria-label="Who starts AI calls">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {(Object.keys(CALL_AUTOMATION_MODE_LABELS) as CallAutomationMode[]).map((mode) => (
                        <SelectItem key={mode} value={mode}>
                          {CALL_AUTOMATION_MODE_LABELS[mode]}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </SettingField>
              <SettingField
                title="Call automatically from"
                description="Calls for lower risk tiers are only suggested. Which tiers get a call at all is set in Policy by risk tier."
              >
                <Select
                  value={auto.min_tier ?? 'all'}
                  onValueChange={(tier) => update({ min_tier: tier === 'all' ? null : (tier as RiskTier) })}
                >
                  <SelectTrigger className="w-full" aria-label="Call automatically from">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectItem value="all">Every tier</SelectItem>
                      {AUTO_TIERS.map((tier) => (
                        <SelectItem key={tier} value={tier}>
                          {RISK_TIER_LABELS[tier]} risk and above
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </SettingField>
              <SettingField
                title="Sales channels"
                description="Orders from unticked channels are only suggested."
              >
                <div className="flex flex-wrap gap-x-4 gap-y-2">
                  {CHANNELS.map((channel) => {
                    const on = auto.channels == null || auto.channels.includes(channel)
                    return (
                      <label key={channel} className="flex items-center gap-2 text-sm">
                        <Checkbox
                          checked={on}
                          onCheckedChange={(checked) => {
                            const current = auto.channels ?? CHANNELS
                            const next = checked
                              ? [...current, channel]
                              : current.filter((c) => c !== channel)
                            update({ channels: next.length === CHANNELS.length ? null : next })
                          }}
                        />
                        {SALES_CHANNEL_LABELS[channel]}
                      </label>
                    )
                  })}
                </div>
              </SettingField>
              <SettingField
                title="Amount to collect"
                description="Auto-call only orders in this range; leave a box empty for no limit."
                contentClassName="@md/field-group:w-[26rem]"
              >
                <div className="grid grid-cols-[3rem_1fr_1fr] items-center gap-2">
                  {CURRENCIES.map((cur) => (
                    <div key={cur} className="contents">
                      <span className="text-sm text-muted-foreground">{cur}</span>
                      {(['min', 'max'] as const).map((bound) => (
                        <Input
                          key={bound}
                          aria-label={`${bound === 'min' ? 'Minimum' : 'Maximum'} ${cur}`}
                          placeholder={bound === 'min' ? 'From' : 'Up to'}
                          inputMode={cur === 'VND' ? 'numeric' : 'decimal'}
                          className="text-right tabular-nums"
                          value={ranges[cur]![bound]}
                          onChange={(event) =>
                            setRanges((r) => ({ ...r, [cur]: { ...r[cur]!, [bound]: event.target.value } }))
                          }
                        />
                      ))}
                    </div>
                  ))}
                </div>
                {!rangesValid && (
                  <p className="text-xs text-destructive">The minimum is above the maximum.</p>
                )}
              </SettingField>
              <SettingField
                title="Call only at set times"
                description="Local time of the order's branch. Off: whenever contact hours allow."
                contentClassName="@md/field-group:w-[26rem]"
              >
                <div className="flex flex-col gap-2">
                  <Switch
                    aria-label="Call only at set times"
                    checked={!!callWindow}
                    onCheckedChange={(on) =>
                      update({ call_window: on ? { start: '09:00', end: '20:00', days: WEEKDAYS } : null })
                    }
                  />
                  {callWindow && (
                    <>
                      <div className="flex items-center gap-2">
                        <Input
                          type="time"
                          aria-label="Calls from"
                          value={callWindow.start ?? '08:00'}
                          min="08:00"
                          max="21:00"
                          onChange={(event) =>
                            update({ call_window: { ...callWindow, start: event.target.value } })
                          }
                        />
                        <span className="text-muted-foreground">–</span>
                        <Input
                          type="time"
                          aria-label="Calls until"
                          value={callWindow.end ?? '21:00'}
                          min="08:00"
                          max="21:00"
                          onChange={(event) =>
                            update({ call_window: { ...callWindow, end: event.target.value } })
                          }
                        />
                      </div>
                      <ToggleGroup
                        type="multiple"
                        variant="outline"
                        size="sm"
                        value={callWindow.days ?? WEEKDAYS}
                        onValueChange={(days) =>
                          update({ call_window: { ...callWindow, days: days as Weekday[] } })
                        }
                        aria-label="Days"
                      >
                        {WEEKDAYS.map((day) => (
                          <ToggleGroupItem key={day} value={day}>
                            {WEEKDAY_LABELS[day]}
                          </ToggleGroupItem>
                        ))}
                      </ToggleGroup>
                      {!windowValid && (
                        <p className="text-xs text-destructive">
                          Pick at least one day and hours within 08:00–21:00.
                        </p>
                      )}
                    </>
                  )}
                </div>
              </SettingField>
              <SettingField title="AI calls per order" description="At most 2, by contact protection.">
                <Select
                  value={String(auto.max_attempts)}
                  onValueChange={(value) => update({ max_attempts: Number(value) })}
                >
                  <SelectTrigger className="w-full" aria-label="AI calls per order">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectItem value="1">1 call</SelectItem>
                      <SelectItem value="2">2 calls</SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </SettingField>
              <SettingField
                title="Wait before calling again"
                description="At least 30 minutes between two calls."
                last
              >
                <InputGroup>
                  <InputGroupInput
                    aria-label="Wait before calling again"
                    type="number"
                    min={30}
                    max={1440}
                    value={auto.retry_after_minutes}
                    onChange={(event) => update({ retry_after_minutes: Number(event.target.value) || 0 })}
                  />
                  <InputGroupAddon align="inline-end">
                    <InputGroupText>min</InputGroupText>
                  </InputGroupAddon>
                </InputGroup>
              </SettingField>
            </FieldGroup>
          </fieldset>
        </FramePanel>
        <FrameFooter className="flex-row items-center justify-between gap-3 px-2! py-2.5!">
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <InfoIcon className="size-3.5" aria-hidden="true" />
            Orders that already have a decision keep the old rules.
          </span>
          <Button type="submit" disabled={!canEdit || !valid || mutation.isPending}>
            {mutation.isPending && <Spinner data-icon="inline-start" />}
            Save new version
          </Button>
        </FrameFooter>
      </Frame>
    </form>
  )
}

// ── History ──

function PolicyHistory({ versions }: { versions: Policy[] }) {
  return (
    <Frame className="w-full">
      <FrameHeader className="px-2! py-2.5!">
        <FrameTitle>Policy change history</FrameTitle>
        <FrameDescription>
          Who changed what, and when. Each decision records the policy version it used.
        </FrameDescription>
      </FrameHeader>
      <FramePanel>
        <Timeline defaultValue={versions.length} className="gap-0">
          {versions.map((version, index) => {
            const previous = versions[index + 1]
            const changes = previous
              ? version.tiers.filter((t, i) => JSON.stringify(t) !== JSON.stringify(previous.tiers[i]))
              : []
            const automationChanged =
              !!previous && JSON.stringify(version.automation) !== JSON.stringify(previous.automation)
            return (
              <TimelineItem
                key={version.version}
                step={index + 1}
                className="group-data-[orientation=vertical]/timeline:ms-5 group-data-[orientation=vertical]/timeline:not-last:pb-5"
              >
                {index < versions.length - 1 && (
                  <TimelineSeparator className="bg-input group-data-[orientation=vertical]/timeline:-left-3 group-data-[orientation=vertical]/timeline:h-[calc(100%-1.5rem)] group-data-[orientation=vertical]/timeline:-translate-x-1/2 group-data-[orientation=vertical]/timeline:translate-y-5.5" />
                )}
                <TimelineIndicator className="size-2.5 border-0 bg-foreground group-data-[orientation=vertical]/timeline:top-1.25 group-data-[orientation=vertical]/timeline:-left-3 group-data-[orientation=vertical]/timeline:-translate-x-1/2" />
                <TimelineContent className="ps-3">
                  <p className="text-sm font-medium">
                    Version {version.version}
                    {index === 0 && (
                      <Badge variant="success-light" size="sm" className="ms-2">
                        In use
                      </Badge>
                    )}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatDateTime(version.effective_from)} ·{' '}
                    {version.updated_by === 'system' ? 'System default' : version.updated_by}
                  </p>
                  {automationChanged && <p className="mt-1.5 text-xs">Call automation changed</p>}
                  {changes.length > 0 && (
                    <ul className="mt-1.5 flex flex-col gap-1 text-xs">
                      {changes.map((t) => (
                        <li key={t.tier}>
                          {RISK_TIER_LABELS[t.tier]}: {DECISION_ACTION_LABELS[t.action]}
                          {t.if_no_response &&
                            `, if no response after ${t.no_response_after_minutes} min → ${DECISION_ACTION_LABELS[t.if_no_response]}`}
                        </li>
                      ))}
                    </ul>
                  )}
                </TimelineContent>
              </TimelineItem>
            )
          })}
        </Timeline>
      </FramePanel>
    </Frame>
  )
}
