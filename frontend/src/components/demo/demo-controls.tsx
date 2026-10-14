import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { ExternalLinkIcon, RotateCcwIcon, ShieldAlertIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import type { SpamSimulationResult } from '@/api/gen'
import {
  getMeOptions,
  resetDemoMutation,
  runSpamSimulationMutation,
} from '@/api/gen/@tanstack/react-query.gen'
import { SettingField } from '@/components/blocks/settings-3/components/setting-field'
import { Badge } from '@/components/reui/badge'
import { Frame, FrameDescription, FrameHeader, FramePanel, FrameTitle } from '@/components/reui/frame'
import { Button } from '@/components/ui/button'
import { FieldGroup } from '@/components/ui/field'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { problemMessage } from '@/lib/api'
import { mockMode } from '@/mocks/fetch'

// Demo controls for the hackathon (E1.3 reset, E9.4 spam simulation), laid out with the
// setting rows of ReUI settings-3. Mock-only switches are marked "mock".

export function DemoControls() {
  const queryClient = useQueryClient()
  const [spam, setSpam] = useState<SpamSimulationResult | null>(null)
  const refreshAll = () => queryClient.invalidateQueries()

  const reset = useMutation({
    ...resetDemoMutation(),
    onSuccess: (result) => {
      setSpam(null)
      toast.success('Đã đặt lại dữ liệu demo', { description: `${result.orders} đơn, seed ${result.seed}` })
      void refreshAll()
    },
    onError: (error) => toast.error('Không đặt lại được', { description: problemMessage(error) }),
  })
  const simulate = useMutation({
    ...runSpamSimulationMutation(),
    onSuccess: (result) => {
      setSpam(result)
      void refreshAll()
    },
    onError: (error) => toast.error('Không chạy được mô phỏng', { description: problemMessage(error) }),
  })

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          Demo
          {mockMode === 'all' && <Badge variant="warning-light">Dữ liệu mẫu</Badge>}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">Công cụ cho buổi demo. Không dùng cho shop thật.</p>
      </div>

      <Frame className="w-full">
        <FrameHeader className="px-2! py-2.5!">
          <FrameTitle>Kịch bản demo</FrameTitle>
          <FrameDescription>
            Chạy lại cho ra cùng kết quả: dữ liệu sinh từ seed cố định, không có SĐT thật.
          </FrameDescription>
        </FrameHeader>
        <FramePanel className="p-0">
          <FieldGroup className="gap-0">
            <SettingField
              title="Đặt lại dữ liệu demo"
              description="Xóa thay đổi trong phiên và nạp lại bộ đơn mẫu cố định."
            >
              <Button variant="outline" onClick={() => reset.mutate({})} disabled={reset.isPending}>
                {reset.isPending ? (
                  <Spinner data-icon="inline-start" />
                ) : (
                  <RotateCcwIcon aria-hidden="true" />
                )}
                Đặt lại
              </Button>
            </SettingField>
            <SettingField
              title="Mô phỏng tấn công spam"
              description="50 đơn từ 20 tài khoản cùng 1 SĐT. COD Guard gộp và chỉ liên hệ đúng 1 lần, rồi chặn SĐT."
              badge={{ label: 'E9.4', variant: 'info-light' }}
            >
              <Button onClick={() => simulate.mutate({})} disabled={simulate.isPending}>
                {simulate.isPending ? (
                  <Spinner data-icon="inline-start" />
                ) : (
                  <ShieldAlertIcon aria-hidden="true" />
                )}
                Chạy mô phỏng
              </Button>
            </SettingField>
            {spam && (
              <div className="grid grid-cols-2 gap-3 px-4 py-4 sm:grid-cols-4">
                <Stat label="Đơn spam" value={spam.orders_created} />
                <Stat label="Tài khoản" value={spam.accounts} />
                <Stat label="Lần liên hệ" value={spam.contacts_made} highlight />
                <Stat
                  label={`SĐT ${spam.phone_masked}`}
                  value={spam.phone_blocked ? 'Đã chặn' : 'Chưa chặn'}
                  highlight
                />
                <Button variant="link" size="sm" className="col-span-full justify-start p-0" asChild>
                  <Link to="/orders" search={{ status: ['pending_review'] }}>
                    Xem các đơn spam trong hàng chờ duyệt
                  </Link>
                </Button>
              </div>
            )}
            <RoleSwitch />
            <BuyerLinks />
          </FieldGroup>
        </FramePanel>
      </Frame>
    </div>
  )
}

function Stat({
  label,
  value,
  highlight = false,
}: {
  label: string
  value: number | string
  highlight?: boolean
}) {
  return (
    <div className="rounded-lg border p-3">
      <div className="truncate text-xs text-muted-foreground">{label}</div>
      <div className={highlight ? 'text-xl font-semibold text-success' : 'text-xl font-semibold'}>
        {value}
      </div>
    </div>
  )
}

/** Mock only: view the app as a staff member to see the read-only settings (E7.7). */
function RoleSwitch() {
  const queryClient = useQueryClient()
  const { data: me } = useQuery(getMeOptions())
  if (mockMode === 'off') return null
  return (
    <SettingField
      title="Vai trò đang xem"
      description="Nhân viên không sửa được chi phí và policy."
      badge={{ label: 'mock', variant: 'warning-light' }}
    >
      <Select
        value={me?.role ?? 'owner'}
        onValueChange={async (role) => {
          const { mockDb } = await import('@/mocks/db')
          mockDb.role = role as 'owner' | 'staff'
          await queryClient.invalidateQueries()
          toast.info(role === 'owner' ? 'Đang xem với quyền chủ shop' : 'Đang xem với quyền nhân viên')
        }}
      >
        <SelectTrigger className="w-full" aria-label="Vai trò">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectItem value="owner">Chủ shop</SelectItem>
            <SelectItem value="staff">Nhân viên</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
    </SettingField>
  )
}

/** Mock only: open links to the buyer page for orders that are waiting for the buyer. */
function BuyerLinks() {
  const [links, setLinks] = useState<{ token: string; label: string }[]>([])
  useEffect(() => {
    if (mockMode === 'off') return
    void import('@/mocks/db').then(({ mockDb }) =>
      setLinks(
        [...mockDb.orders.values()]
          .filter(
            (o) => o.confirmation_token && ['awaiting_confirmation', 'awaiting_deposit'].includes(o.status),
          )
          .slice(0, 4)
          .map((o) => ({ token: o.confirmation_token!, label: `${o.external_id} · ${o.buyer_name}` })),
      ),
    )
  }, [])
  if (links.length === 0) return null
  return (
    <SettingField
      title="Trang xác nhận của người mua"
      description="Mở như người mua nhận link qua Zalo ZNS / SMS. Không cần đăng nhập."
      badge={{ label: 'mock', variant: 'warning-light' }}
      last
    >
      <ul className="flex flex-col gap-1.5">
        {links.map((link) => (
          <li key={link.token}>
            <Link
              to="/c/$token"
              params={{ token: link.token }}
              target="_blank"
              className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
            >
              {link.label}
              <ExternalLinkIcon className="size-3.5" aria-hidden="true" />
            </Link>
          </li>
        ))}
      </ul>
    </SettingField>
  )
}
