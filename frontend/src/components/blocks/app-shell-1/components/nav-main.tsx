import { useQuery } from '@tanstack/react-query'
import { Link, useMatchRoute } from '@tanstack/react-router'

import { listOrdersOptions } from '@/api/gen/@tanstack/react-query.gen'
import { Badge } from '@/components/reui/badge'
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar'

import { NAV_MAIN, type NavItem } from './data'

function usePendingReviewCount() {
  const { data } = useQuery(listOrdersOptions({ query: { status: ['pending_review'], limit: 1 } }))
  return data?.total
}

function LeafNavItem({ item, badge }: { item: NavItem; badge?: number }) {
  const matchRoute = useMatchRoute()
  const isActive = Boolean(matchRoute({ to: item.to, fuzzy: !item.exact }))
  return (
    <SidebarMenuItem>
      <SidebarMenuButton tooltip={item.label} isActive={isActive} asChild>
        <Link to={item.to}>
          {item.icon}
          <span>{item.label}</span>
          {badge !== undefined && badge > 0 && (
            <SidebarMenuBadge>
              <Badge variant="warning-light" size="sm">
                {badge}
              </Badge>
            </SidebarMenuBadge>
          )}
        </Link>
      </SidebarMenuButton>
    </SidebarMenuItem>
  )
}

export function NavMain() {
  const pendingReview = usePendingReviewCount()
  return (
    <SidebarGroup>
      <SidebarGroupLabel>Vận hành</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu className="gap-1!">
          {NAV_MAIN.map((item) => (
            <LeafNavItem key={item.id} item={item} badge={item.id === 'review' ? pendingReview : undefined} />
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}
