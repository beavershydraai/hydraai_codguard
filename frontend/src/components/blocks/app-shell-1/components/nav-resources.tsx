import { Link, useSearch } from '@tanstack/react-router'
import { ChevronDownIcon } from 'lucide-react'
import { useState } from 'react'

import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar'
import { cn } from '@/lib/utils'

import { TIER_SHORTCUTS, type TierShortcut } from './data'

function ResourceDot({ color }: { color: string }) {
  return <span className={cn('mr-1 ml-1.5 size-1.5 shrink-0 rounded-full', color)} aria-hidden="true" />
}

function ResourceItem({ shortcut, isActive }: { shortcut: TierShortcut; isActive: boolean }) {
  return (
    <SidebarMenuItem>
      <SidebarMenuButton tooltip={`${shortcut.name} risk`} isActive={isActive} asChild>
        <Link to="/orders" search={{ tier: [shortcut.tier] }}>
          <ResourceDot color={shortcut.color} />
          <span className="min-w-0 truncate">{shortcut.name}</span>
        </Link>
      </SidebarMenuButton>
    </SidebarMenuItem>
  )
}

function ResourceList() {
  // Highlights the shortcut matching the order inbox's tier filter.
  const search = useSearch({ strict: false })
  const tiers = 'tier' in search ? search.tier : undefined
  const activeTier = tiers?.length === 1 ? tiers[0] : undefined
  return (
    <SidebarGroupContent id="tier-shortcuts-list">
      <SidebarMenu className="gap-0.25">
        {TIER_SHORTCUTS.map((shortcut) => (
          <ResourceItem key={shortcut.tier} shortcut={shortcut} isActive={activeTier === shortcut.tier} />
        ))}
      </SidebarMenu>
    </SidebarGroupContent>
  )
}

export function NavResources() {
  const [open, setOpen] = useState(true)

  return (
    <SidebarGroup className="group-data-[collapsible=icon]:hidden">
      <SidebarGroupLabel
        asChild
        className="w-full cursor-pointer focus-visible:ring-2 focus-visible:ring-sidebar-ring focus-visible:outline-none"
      >
        <button
          onClick={() => setOpen((prev) => !prev)}
          aria-expanded={open}
          aria-controls="tier-shortcuts-list"
        >
          Orders by risk tier
          <ChevronDownIcon
            className={cn(
              'ml-auto size-4 shrink-0 opacity-60 transition-transform duration-200',
              !open && '-rotate-90',
            )}
            aria-hidden="true"
          />
        </button>
      </SidebarGroupLabel>
      {open && <ResourceList />}
    </SidebarGroup>
  )
}
