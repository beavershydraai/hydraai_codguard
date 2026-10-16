import { Link, useMatchRoute } from '@tanstack/react-router'

import { SidebarGroup, SidebarMenu, SidebarMenuButton, SidebarMenuItem } from '@/components/ui/sidebar'

import { NAV_SECONDARY, type NavItem } from './data'

function SecondaryNavItem({ item }: { item: NavItem }) {
  const matchRoute = useMatchRoute()
  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        size="sm"
        tooltip={item.label}
        isActive={Boolean(matchRoute({ to: item.to, fuzzy: true }))}
        render={<Link to={item.to} />}
        className="[&_svg]:size-3.5"
      >
        {item.icon}
        <span>{item.label}</span>
      </SidebarMenuButton>
    </SidebarMenuItem>
  )
}

export function NavSecondary() {
  return (
    <SidebarGroup>
      <SidebarMenu>
        {NAV_SECONDARY.map((item) => (
          <SecondaryNavItem key={item.id} item={item} />
        ))}
      </SidebarMenu>
    </SidebarGroup>
  )
}
