import { useQuery, useQueryClient } from '@tanstack/react-query'
import { BotIcon, PhoneIcon, PhoneOffIcon, UserIcon } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import type { Call, CallOutcome, OrderDetail } from '@/api/gen'
import { getCallOptions } from '@/api/gen/@tanstack/react-query.gen'
import { Badge } from '@/components/reui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { invalidate } from '@/lib/api'
import { CALL_OUTCOME_LABELS, CALL_STATUS_LABELS, formatVnd } from '@/lib/labels'
import { cn } from '@/lib/utils'

// Browser phone for the AI confirmation call (E5.2). Until the Gemini Live session (E5) is wired,
// the conversation is scripted and the "buyer" picks the replies; the script follows the call
// rules in AGENTS.md: the assistant says it is automated and names the shop, checks it is talking
// to the buyer before giving order details, reads changes back, never mentions risk or scores and
// never asks for money or codes. The call ends with exactly one of the 7 outcomes.

type Line = { from: 'ai' | 'buyer'; text: string }
type Stage = 'ringing' | 'verify' | 'summary' | 'edit' | 'confirm_edit' | 'confirm_cancel' | 'done'

const OUTCOME_SUMMARY: Record<CallOutcome, (change?: string) => string> = {
  confirmed: () => 'The buyer confirmed the order, with the right items and address.',
  edited: (change) =>
    `The buyer confirmed the order and changed the delivery address: ${change}. The AI read the new address back.`,
  cancelled: () => 'The buyer no longer wants the order and confirmed the cancellation.',
  not_ordered: () =>
    'The person who answered says they did not place this order. The phone is blocked from contact for 30 days.',
  no_answer: () => 'No answer.',
  wrong_person: () => 'The person who answered is not the buyer; the AI gave no order details.',
  unclear: () => 'The call dropped midway; it is unclear whether the buyer will accept the order.',
}

export function CallSimulator({
  order,
  call,
  shopName,
  onOpenChange,
}: {
  order: OrderDetail
  call: Call | null
  shopName: string
  onOpenChange: (open: boolean) => void
}) {
  const [simulated, setSimulated] = useState<boolean | null>(null)

  useEffect(() => {
    if (!call) return
    let live = true
    void import('@/mocks/db').then(({ mockDb }) => {
      if (live) setSimulated(mockDb.calls.has(call.id))
    })
    return () => {
      live = false
    }
  }, [call])

  return (
    <Dialog open={!!call} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            AI confirmation call
            {simulated && <Badge variant="warning-light">mock</Badge>}
          </DialogTitle>
          <DialogDescription>
            {simulated
              ? 'Simulated phone: you play the buyer and pick the replies.'
              : 'The backend places the call; the status updates automatically.'}
          </DialogDescription>
        </DialogHeader>
        {call && simulated === true && <ScriptedCall order={order} call={call} shopName={shopName} />}
        {call && simulated === false && <LiveCallStatus call={call} />}
      </DialogContent>
    </Dialog>
  )
}

const FINISHED = new Set<Call['status']>(['completed', 'failed'])

function LiveCallStatus({ call }: { call: Call }) {
  const { data = call } = useQuery({
    ...getCallOptions({ path: { call_id: call.id } }),
    refetchInterval: (query) => (FINISHED.has(query.state.data?.status ?? 'queued') ? false : 2_000),
  })
  return (
    <div className="flex flex-col items-center gap-2 py-6 text-center">
      <PhoneIcon className="size-8 text-muted-foreground" aria-hidden="true" />
      <p className="font-medium">{data.phone_masked}</p>
      <Badge variant="info-outline">{CALL_STATUS_LABELS[data.status]}</Badge>
      {data.outcome && <p className="text-sm">Outcome: {CALL_OUTCOME_LABELS[data.outcome]}</p>}
      {data.summary_vi && <p className="text-sm text-muted-foreground">{data.summary_vi}</p>}
    </div>
  )
}

function ScriptedCall({ order, call, shopName }: { order: OrderDetail; call: Call; shopName: string }) {
  const queryClient = useQueryClient()
  const [stage, setStage] = useState<Stage>('ringing')
  const [lines, setLines] = useState<Line[]>([])
  const [outcome, setOutcome] = useState<CallOutcome | null>(null)
  const [newAddress, setNewAddress] = useState('')
  const [seconds, setSeconds] = useState(0)
  const scroller = useRef<HTMLDivElement>(null)

  const talking = stage !== 'ringing' && stage !== 'done'
  useEffect(() => {
    if (!talking) return
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(timer)
  }, [talking])
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: 'smooth' })
  }, [lines])

  const name = order.buyer_name.split(' ').pop()
  const items = order.items
    .map((i) => `${i.quantity} ${i.name}${i.variant ? ` (${i.variant})` : ''}`)
    .join(', ')

  const say = (...next: Line[]) => setLines((current) => [...current, ...next])

  const progress = async (result?: CallOutcome, change?: string) => {
    const { mockDb } = await import('@/mocks/db')
    mockDb.progressCall(call.id, result, result ? OUTCOME_SUMMARY[result](change) : undefined, change)
    void invalidate(queryClient, 'getOrder', 'listOrders', 'getCall')
  }

  const finish = (result: CallOutcome, buyer: string | null, ai: string, change?: string) => {
    say(...(buyer ? [{ from: 'buyer' as const, text: buyer }] : []), { from: 'ai', text: ai })
    setOutcome(result)
    setStage('done')
    void progress(result, change)
  }

  const answer = () => {
    setStage('verify')
    void progress()
    say({
      from: 'ai',
      text: `Hello, this is the automated assistant for ${shopName}. Am I speaking with ${name}?`,
    })
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Phone header */}
      <div className="flex items-center justify-between rounded-xl bg-muted px-4 py-3">
        <div className="flex flex-col">
          <span className="text-sm font-medium tabular-nums">{call.phone_masked}</span>
          <span className="text-xs text-muted-foreground">
            Attempt {call.attempt} ·{' '}
            {stage === 'ringing' ? 'Ringing…' : stage === 'done' ? 'Ended' : 'In call'}
          </span>
        </div>
        <span className="font-mono text-sm tabular-nums">
          {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}
        </span>
      </div>

      {/* Transcript */}
      <div
        ref={scroller}
        className="flex max-h-72 min-h-40 flex-col gap-2 overflow-y-auto"
        aria-live="polite"
      >
        {lines.length === 0 && (
          <p className="m-auto text-sm text-muted-foreground">The buyer has not answered yet.</p>
        )}
        {lines.map((line, i) => (
          <div key={i} className={cn('flex items-end gap-2', line.from === 'buyer' && 'flex-row-reverse')}>
            <span
              className={cn(
                'flex size-6 shrink-0 items-center justify-center rounded-full',
                line.from === 'ai' ? 'bg-primary text-primary-foreground' : 'bg-muted',
              )}
              aria-hidden="true"
            >
              {line.from === 'ai' ? <BotIcon className="size-3.5" /> : <UserIcon className="size-3.5" />}
            </span>
            <p
              className={cn(
                'max-w-[80%] rounded-2xl px-3 py-2 text-sm',
                line.from === 'ai'
                  ? 'rounded-bl-sm bg-muted'
                  : 'rounded-br-sm bg-primary text-primary-foreground',
              )}
            >
              <span className="sr-only">{line.from === 'ai' ? 'AI: ' : 'Buyer: '}</span>
              {line.text}
            </p>
          </div>
        ))}
      </div>

      {/* Buyer replies */}
      <div className="flex flex-wrap gap-2">
        {stage === 'ringing' && (
          <>
            <Button onClick={answer}>
              <PhoneIcon aria-hidden="true" />
              Answer
            </Button>
            <Button variant="outline" onClick={() => finish('no_answer', null, '(No one answered.)')}>
              <PhoneOffIcon aria-hidden="true" />
              Don't answer
            </Button>
          </>
        )}
        {stage === 'verify' && (
          <>
            <Button
              onClick={() => {
                say(
                  { from: 'buyer', text: 'Yes, speaking.' },
                  {
                    from: 'ai',
                    text: `Thank you. ${shopName} is calling to confirm order ${order.external_id ?? ''}: ${items}, delivered to ${order.address.raw}, with ${formatVnd(order.cod_amount_vnd)} to pay on delivery. Can you confirm you will accept it?`,
                  },
                )
                setStage('summary')
              }}
            >
              Yes, speaking
            </Button>
            <Button
              variant="outline"
              onClick={() =>
                finish(
                  'wrong_person',
                  'No, I think you have the wrong number.',
                  'Sorry to have bothered you. Have a nice day.',
                )
              }
            >
              Not me
            </Button>
          </>
        )}
        {stage === 'summary' && (
          <>
            <Button
              onClick={() =>
                finish(
                  'confirmed',
                  'Yes, please go ahead and deliver it.',
                  'Thank you. The shop will ship your order soon.',
                )
              }
            >
              Confirm
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                say(
                  { from: 'buyer', text: 'Could you change the delivery address, please?' },
                  { from: 'ai', text: 'Of course. Please tell me the new address.' },
                )
                setStage('edit')
              }}
            >
              Change address
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                say(
                  { from: 'buyer', text: "Actually, I don't want it any more." },
                  { from: 'ai', text: 'Just to check: you want to cancel this order?' },
                )
                setStage('confirm_cancel')
              }}
            >
              Cancel order
            </Button>
            <Button
              variant="outline"
              onClick={() =>
                finish(
                  'not_ordered',
                  "I didn't order anything.",
                  "I'm sorry for the trouble. The shop will cancel the order and won't contact this number again.",
                )
              }
            >
              I didn't order this
            </Button>
            <Button
              variant="ghost"
              onClick={() => finish('unclear', '(Hangs up midway.)', '(The call dropped.)')}
            >
              Hang up
            </Button>
          </>
        )}
        {stage === 'edit' && (
          <form
            className="flex w-full gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              if (newAddress.trim().length < 5) return
              say(
                { from: 'buyer', text: newAddress.trim() },
                {
                  from: 'ai',
                  text: `Let me read the new address back: ${newAddress.trim()}. Is that correct?`,
                },
              )
              setStage('confirm_edit')
            }}
          >
            <Input
              autoFocus
              value={newAddress}
              onChange={(event) => setNewAddress(event.target.value)}
              placeholder="New address"
              aria-label="New address"
            />
            <Button type="submit">Send</Button>
          </form>
        )}
        {stage === 'confirm_edit' && (
          <Button
            onClick={() =>
              finish(
                'edited',
                "Yes, that's right.",
                'Thank you. The shop has updated the address and will ship your order.',
                newAddress.trim(),
              )
            }
          >
            That's right
          </Button>
        )}
        {stage === 'confirm_cancel' && (
          <>
            <Button
              variant="destructive"
              onClick={() =>
                finish(
                  'cancelled',
                  'Yes, please cancel it.',
                  'The shop has cancelled the order. Thank you for letting us know.',
                )
              }
            >
              Yes, cancel order
            </Button>
            <Button
              variant="outline"
              onClick={() =>
                finish(
                  'confirmed',
                  "Actually, I'll keep it.",
                  'The shop will keep the order and ship it soon. Thank you!',
                )
              }
            >
              No, keep order
            </Button>
          </>
        )}
        {stage === 'done' && outcome && (
          <div className="flex w-full flex-col gap-1 rounded-lg border p-3">
            <span className="text-xs text-muted-foreground">Outcome saved to the order</span>
            <span className="font-medium">{CALL_OUTCOME_LABELS[outcome]}</span>
            <span className="text-sm text-muted-foreground">
              {OUTCOME_SUMMARY[outcome](newAddress.trim())}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
