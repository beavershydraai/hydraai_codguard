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
  confirmed: () => 'Người mua xác nhận đơn, đúng sản phẩm và địa chỉ.',
  edited: (change) => `Người mua xác nhận đơn và đổi địa chỉ giao: ${change}. AI đã đọc lại địa chỉ mới.`,
  cancelled: () => 'Người mua không muốn nhận hàng nữa và xác nhận hủy đơn.',
  not_ordered: () => 'Người nghe máy nói không đặt đơn này. SĐT bị chặn liên hệ 30 ngày.',
  no_answer: () => 'Không nghe máy.',
  wrong_person: () => 'Người nghe máy không phải người đặt hàng; AI không đọc thông tin đơn.',
  unclear: () => 'Cuộc gọi bị ngắt giữa chừng, chưa rõ người mua có nhận hàng không.',
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
            AI gọi xác nhận
            {simulated && <Badge variant="warning-light">mock</Badge>}
          </DialogTitle>
          <DialogDescription>
            {simulated
              ? 'Điện thoại giả lập: bạn đóng vai người mua và chọn câu trả lời.'
              : 'Cuộc gọi do backend thực hiện; trạng thái cập nhật tự động.'}
          </DialogDescription>
        </DialogHeader>
        {call && simulated === true && <ScriptedCall order={order} call={call} shopName={shopName} />}
        {call && simulated === false && <LiveCallStatus call={call} />}
      </DialogContent>
    </Dialog>
  )
}

function LiveCallStatus({ call }: { call: Call }) {
  const { data = call } = useQuery({
    ...getCallOptions({ path: { call_id: call.id } }),
    refetchInterval: (query) => (query.state.data?.status === 'completed' ? false : 2_000),
  })
  return (
    <div className="flex flex-col items-center gap-2 py-6 text-center">
      <PhoneIcon className="size-8 text-muted-foreground" aria-hidden="true" />
      <p className="font-medium">{data.phone_masked}</p>
      <Badge variant="info-outline">{CALL_STATUS_LABELS[data.status]}</Badge>
      {data.outcome && <p className="text-sm">Kết quả: {CALL_OUTCOME_LABELS[data.outcome]}</p>}
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
      text: `Xin chào, đây là trợ lý tự động của ${shopName}. Cho tôi hỏi có phải anh/chị ${name} không ạ?`,
    })
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Phone header */}
      <div className="flex items-center justify-between rounded-xl bg-muted px-4 py-3">
        <div className="flex flex-col">
          <span className="text-sm font-medium tabular-nums">{call.phone_masked}</span>
          <span className="text-xs text-muted-foreground">
            Lần gọi {call.attempt} ·{' '}
            {stage === 'ringing' ? 'Đang đổ chuông…' : stage === 'done' ? 'Đã kết thúc' : 'Đang nói chuyện'}
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
          <p className="m-auto text-sm text-muted-foreground">Người mua chưa nghe máy.</p>
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
              <span className="sr-only">{line.from === 'ai' ? 'AI: ' : 'Người mua: '}</span>
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
              Nghe máy
            </Button>
            <Button variant="outline" onClick={() => finish('no_answer', null, '(Không ai nghe máy.)')}>
              <PhoneOffIcon aria-hidden="true" />
              Không nghe máy
            </Button>
          </>
        )}
        {stage === 'verify' && (
          <>
            <Button
              onClick={() => {
                say(
                  { from: 'buyer', text: 'Đúng rồi, tôi đây.' },
                  {
                    from: 'ai',
                    text: `Dạ, ${shopName} gọi xác nhận đơn ${order.external_id ?? ''} gồm ${items}, giao tới ${order.address.raw}, thu hộ ${formatVnd(order.cod_amount_vnd)}. Anh/chị xác nhận nhận hàng chứ ạ?`,
                  },
                )
                setStage('summary')
              }}
            >
              Đúng, tôi đây
            </Button>
            <Button
              variant="outline"
              onClick={() =>
                finish(
                  'wrong_person',
                  'Không phải, chắc nhầm số rồi.',
                  'Dạ, xin lỗi đã làm phiền anh/chị. Chúc anh/chị một ngày tốt lành.',
                )
              }
            >
              Không phải tôi
            </Button>
          </>
        )}
        {stage === 'summary' && (
          <>
            <Button
              onClick={() =>
                finish(
                  'confirmed',
                  'Đúng rồi, em giao giúp chị nhé.',
                  'Dạ, shop sẽ gửi hàng sớm. Cảm ơn anh/chị!',
                )
              }
            >
              Xác nhận
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                say(
                  { from: 'buyer', text: 'Đổi giúp chị địa chỉ giao nhé.' },
                  { from: 'ai', text: 'Dạ, anh/chị đọc giúp tôi địa chỉ mới ạ.' },
                )
                setStage('edit')
              }}
            >
              Đổi địa chỉ
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                say(
                  { from: 'buyer', text: 'Thôi chị không lấy nữa.' },
                  { from: 'ai', text: 'Dạ, anh/chị muốn hủy đơn này đúng không ạ?' },
                )
                setStage('confirm_cancel')
              }}
            >
              Hủy đơn
            </Button>
            <Button
              variant="outline"
              onClick={() =>
                finish(
                  'not_ordered',
                  'Tôi không đặt đơn nào cả.',
                  'Dạ, xin lỗi anh/chị. Shop sẽ hủy đơn và không liên hệ số này nữa.',
                )
              }
            >
              Tôi không đặt
            </Button>
            <Button
              variant="ghost"
              onClick={() => finish('unclear', '(Ngắt máy giữa chừng.)', '(Cuộc gọi bị ngắt.)')}
            >
              Ngắt máy
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
                { from: 'ai', text: `Tôi đọc lại địa chỉ mới: ${newAddress.trim()}. Đúng chưa ạ?` },
              )
              setStage('confirm_edit')
            }}
          >
            <Input
              autoFocus
              value={newAddress}
              onChange={(event) => setNewAddress(event.target.value)}
              placeholder="Địa chỉ mới"
              aria-label="Địa chỉ mới"
            />
            <Button type="submit">Gửi</Button>
          </form>
        )}
        {stage === 'confirm_edit' && (
          <Button
            onClick={() =>
              finish(
                'edited',
                'Đúng rồi.',
                'Dạ, shop đã cập nhật địa chỉ và sẽ gửi hàng. Cảm ơn anh/chị!',
                newAddress.trim(),
              )
            }
          >
            Đúng rồi
          </Button>
        )}
        {stage === 'confirm_cancel' && (
          <>
            <Button
              variant="destructive"
              onClick={() =>
                finish('cancelled', 'Ừ, hủy giúp chị.', 'Dạ, shop đã hủy đơn. Cảm ơn anh/chị đã báo.')
              }
            >
              Có, hủy đơn
            </Button>
            <Button
              variant="outline"
              onClick={() =>
                finish(
                  'confirmed',
                  'À thôi, chị vẫn lấy.',
                  'Dạ, shop giữ đơn và gửi hàng sớm. Cảm ơn anh/chị!',
                )
              }
            >
              Không, vẫn nhận
            </Button>
          </>
        )}
        {stage === 'done' && outcome && (
          <div className="flex w-full flex-col gap-1 rounded-lg border p-3">
            <span className="text-xs text-muted-foreground">Kết quả đã ghi vào đơn</span>
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
