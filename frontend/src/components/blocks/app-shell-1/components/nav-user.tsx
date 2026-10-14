import type { ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import {
  LogOutIcon,
  MonitorIcon,
  MoonIcon,
  MoreHorizontalIcon,
  PaletteIcon,
  SettingsIcon,
  SunIcon,
} from 'lucide-react'

import { getMeOptions } from '@/api/gen/@tanstack/react-query.gen'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem, useSidebar } from '@/components/ui/sidebar'
import { signOut } from '@/lib/auth'
import { cn } from '@/lib/utils'
import { type Theme, useThemeStore } from '@/stores/theme'

// ── Constants ──

const ROLE_LABELS = { owner: 'Chủ shop', staff: 'Nhân viên' } as const

const THEMES: { value: Theme; label: string; icon: ReactNode }[] = [
  { value: 'light', label: 'Sáng', icon: <SunIcon className="size-3.5" aria-hidden="true" /> },
  { value: 'dark', label: 'Tối', icon: <MoonIcon className="size-3.5" aria-hidden="true" /> },
  { value: 'system', label: 'Theo hệ thống', icon: <MonitorIcon className="size-3.5" aria-hidden="true" /> },
]

function useCurrentUser() {
  const { data } = useQuery(getMeOptions())
  const name = data?.display_name || data?.email || '…'
  return {
    name,
    email: data?.email ?? '',
    role: data ? ROLE_LABELS[data.role] : '',
    initials: name.charAt(0).toUpperCase(),
  }
}

// ── Theme Toggle ──

function ThemeSegmentedToggle() {
  const currentTheme = useThemeStore((state) => state.theme)
  const setTheme = useThemeStore((state) => state.setTheme)

  return (
    <div
      role="radiogroup"
      aria-label="Giao diện"
      className="inline-flex items-center gap-0.5 rounded-full bg-muted/60 p-0.5"
    >
      {THEMES.map(({ value, label, icon }) => {
        const isActive = currentTheme === value
        return (
          <Button
            key={value}
            type="button"
            role="radio"
            aria-checked={isActive}
            aria-label={label}
            variant="ghost"
            size="icon-xs"
            onClick={() => setTheme(value)}
            className={cn(
              'rounded-full',
              isActive
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {icon}
          </Button>
        )
      })}
    </div>
  )
}

// ── Menu Sections ──

function UserMenuHeader() {
  const user = useCurrentUser()
  return (
    <DropdownMenuLabel className="flex items-center gap-2.5 py-2">
      <Avatar className="size-8 rounded-md">
        <AvatarFallback className="rounded-md">{user.initials}</AvatarFallback>
      </Avatar>
      <div className="flex min-w-0 flex-col">
        <span className="truncate text-sm font-semibold text-foreground">{user.name}</span>
        <span className="truncate text-xs font-normal text-muted-foreground">
          {[user.role, user.email].filter(Boolean).join(' · ')}
        </span>
      </div>
    </DropdownMenuLabel>
  )
}

function UserMenuAccount() {
  return (
    <DropdownMenuGroup>
      <DropdownMenuItem asChild>
        <Link to="/settings">
          <SettingsIcon aria-hidden="true" />
          Cài đặt shop
        </Link>
      </DropdownMenuItem>
    </DropdownMenuGroup>
  )
}

function UserMenuTheme() {
  return (
    <DropdownMenuGroup>
      <DropdownMenuItem className="cursor-default focus:bg-transparent!" onSelect={(e) => e.preventDefault()}>
        <PaletteIcon aria-hidden="true" />
        Giao diện
        <div className="ml-auto">
          <ThemeSegmentedToggle />
        </div>
      </DropdownMenuItem>
    </DropdownMenuGroup>
  )
}

function UserMenuContent() {
  const { isMobile } = useSidebar()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  function handleSignOut() {
    signOut()
    queryClient.clear()
    void navigate({ to: '/login' })
  }

  return (
    <DropdownMenuContent side={isMobile ? 'top' : 'right'} align="end" sideOffset={8} className="w-64">
      <DropdownMenuGroup>
        <UserMenuHeader />
        <DropdownMenuSeparator />
        <UserMenuAccount />
        <DropdownMenuSeparator />
        <UserMenuTheme />
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={handleSignOut}>
          <LogOutIcon aria-hidden="true" />
          Đăng xuất
        </DropdownMenuItem>
      </DropdownMenuGroup>
    </DropdownMenuContent>
  )
}

// ── Nav User ──

export function NavUser() {
  const user = useCurrentUser()
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger
            className="h-auto shrink-0 border border-border bg-background p-1.5 text-sm shadow-sm shadow-black/5 group-data-[collapsible=icon]:justify-center"
            asChild
          >
            <SidebarMenuButton size="lg" aria-label="Mở menu tài khoản">
              <Avatar className="size-6 transition-all duration-300 ease-in-out in-data-[state=collapsed]:size-7!">
                <AvatarFallback className="rounded-md">{user.initials}</AvatarFallback>
              </Avatar>
              <div className="grid min-w-0 flex-1 text-left text-sm leading-tight group-data-[collapsible=icon]:hidden">
                <span className="truncate font-semibold">{user.name}</span>
              </div>
              <MoreHorizontalIcon
                className="mr-1 ml-auto size-4 shrink-0 opacity-50 group-data-[collapsible=icon]:hidden"
                aria-hidden="true"
              />
            </SidebarMenuButton>
          </DropdownMenuTrigger>

          <UserMenuContent />
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
