import { createFileRoute, Link, Outlet } from '@tanstack/react-router'
import { ClipboardCheck, LayoutDashboard, Package, Settings, ShieldCheck } from 'lucide-react'

export const Route = createFileRoute('/_shop')({
  component: ShopLayout,
})

const NAV = [
  { to: '/', label: 'Tổng quan', icon: LayoutDashboard },
  { to: '/orders', label: 'Đơn hàng', icon: Package },
  { to: '/review', label: 'Chờ duyệt', icon: ClipboardCheck },
  { to: '/settings', label: 'Cài đặt', icon: Settings },
] as const

function ShopLayout() {
  return (
    <div className="flex min-h-svh flex-col md:flex-row">
      <aside className="border-b bg-sidebar text-sidebar-foreground md:w-56 md:shrink-0 md:border-r md:border-b-0">
        <div className="flex items-center gap-2 px-4 py-4 font-semibold">
          <ShieldCheck className="size-5 text-primary" />
          COD Guard
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:pb-4">
          {NAV.map(({ to, label, icon: Icon }) => (
            <Link
              key={to}
              to={to}
              activeOptions={{ exact: to === '/' }}
              className="flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground data-[status=active]:bg-sidebar-accent data-[status=active]:font-medium data-[status=active]:text-sidebar-accent-foreground"
            >
              <Icon className="size-4" />
              {label}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-8">
        <Outlet />
      </main>
    </div>
  )
}
