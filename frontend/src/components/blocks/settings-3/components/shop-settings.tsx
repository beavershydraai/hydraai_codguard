import { useMutation, useQueryClient } from '@tanstack/react-query'
import { InfoIcon, LockIcon } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import type { DecisionAction, Policy, RiskTier, Shop, TierPolicy } from '@/api/gen'
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { invalidate, problemMessage } from '@/lib/api'
import { DECISION_ACTION_LABELS, formatDateTime, formatVnd, RISK_TIER_LABELS } from '@/lib/labels'

import { SettingField } from './setting-field'

// Shop settings (E7.1), tier policy (E7.6) and its change history (E4.6), in the setting-row
// grammar of ReUI settings-3 inside tabs like settings-7. Staff can read but not change policy
// or costs (E7.7); the backend enforces it too (403).

export type SettingsTab = 'shop' | 'policy' | 'history'

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
          <TabsTrigger value="history">Change history</TabsTrigger>
        </TabsList>
        <TabsContent value="shop">
          <ShopForm shop={shop} canEdit={canEdit} />
        </TabsContent>
        <TabsContent value="policy">
          <PolicyForm policy={policy} shop={shop} canEdit={canEdit} />
        </TabsContent>
        <TabsContent value="history">
          <PolicyHistory versions={versions} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

// ── Shop and costs ──

function ShopForm({ shop, canEdit }: { shop: Shop; canEdit: boolean }) {
  const queryClient = useQueryClient()
  const s = shop.settings
  const [form, setForm] = useState({
    name: shop.name,
    failed: String(s.failed_delivery_cost_vnd ?? 60_000),
    call: String(s.ai_call_cost_vnd ?? 1_500),
    link: String(s.confirmation_link_cost_vnd ?? 300),
    deposit: String(s.deposit_request_cost_vnd ?? 5_000),
    start: s.contact_hours?.start ?? '08:00',
    end: s.contact_hours?.end ?? '21:00',
  })
  const mutation = useMutation({
    ...updateShopMutation(),
    onSuccess: () => {
      toast.success('Shop settings saved')
      void invalidate(queryClient, 'getShop', 'getDashboardSummary')
    },
    onError: (error) => toast.error('Could not save', { description: problemMessage(error) }),
  })
  const set = (key: keyof typeof form) => (event: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: event.target.value }))
  const money = (value: string) => Math.max(0, Math.round(Number(value.replace(/\D/g, '')) || 0))
  const hoursValid = form.start >= '08:00' && form.end <= '21:00' && form.start < form.end

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        mutation.mutate({
          body: {
            name: form.name.trim(),
            settings: {
              failed_delivery_cost_vnd: money(form.failed),
              ai_call_cost_vnd: money(form.call),
              confirmation_link_cost_vnd: money(form.link),
              deposit_request_cost_vnd: money(form.deposit),
              contact_hours: { start: form.start, end: form.end },
            },
          },
        })
      }}
    >
      <Frame className="w-full">
        <FrameHeader className="px-2! py-2.5!">
          <FrameTitle>Shop &amp; costs</FrameTitle>
          <FrameDescription>
            The defaults work out of the box; adjust them to the shop's real delivery costs.
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
                <Input id="shop-name" value={form.name} onChange={set('name')} required maxLength={100} />
              </SettingField>
              <SettingField
                title="Cost of one failed delivery"
                description="Shipping both ways plus handling. Used to work out each order's expected loss."
                badge={{ label: 'Important', variant: 'destructive-light' }}
                labelFor="cost-failed"
              >
                <MoneyInput id="cost-failed" value={form.failed} onChange={set('failed')} />
              </SettingField>
              <SettingField
                title="Cost of one AI call"
                description="Calls are placed only when the expected loss is higher than this cost."
                labelFor="cost-call"
              >
                <MoneyInput id="cost-call" value={form.call} onChange={set('call')} />
              </SettingField>
              <SettingField
                title="Cost of sending a confirmation link"
                description="Zalo ZNS / SMS message."
                labelFor="cost-link"
              >
                <MoneyInput id="cost-link" value={form.link} onChange={set('link')} />
              </SettingField>
              <SettingField
                title="Cost of requiring a deposit"
                description="Estimated revenue lost when buyers abandon an order because of the deposit."
                labelFor="cost-deposit"
              >
                <MoneyInput id="cost-deposit" value={form.deposit} onChange={set('deposit')} />
              </SettingField>
              <SettingField
                title="Contact hours"
                description="Vietnam time. No contact outside 08:00–21:00."
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
                {!hoursValid && (
                  <p className="text-xs text-destructive">Contact hours must be within 08:00–21:00.</p>
                )}
              </SettingField>
            </FieldGroup>
          </fieldset>
        </FramePanel>
        <FrameFooter className="flex-row items-center justify-between gap-3 px-2! py-2.5!">
          <span className="text-xs text-muted-foreground">
            Order intake API key:{' '}
            {shop.intake_api_key_last4 ? `••••${shop.intake_api_key_last4}` : 'not created'}
          </span>
          <Button type="submit" disabled={!canEdit || !hoursValid || mutation.isPending}>
            {mutation.isPending && <Spinner data-icon="inline-start" />}
            Save changes
          </Button>
        </FrameFooter>
      </Frame>
    </form>
  )
}

function MoneyInput({
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

// ── Tier policy ──

const ACTIONS: DecisionAction[] = [
  'ship_now',
  'send_confirmation_link',
  'ai_call',
  'require_deposit',
  'hold_for_review',
]
const ESCALATIONS: DecisionAction[] = ['ai_call', 'hold_for_review', 'cancel']

function PolicyForm({ policy, shop, canEdit }: { policy: Policy; shop: Shop; canEdit: boolean }) {
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
            expected loss is higher than the contact cost (failed delivery:{' '}
            {formatVnd(shop.settings.failed_delivery_cost_vnd ?? 60_000)}).
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
