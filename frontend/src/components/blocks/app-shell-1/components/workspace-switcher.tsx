import { useQuery } from '@tanstack/react-query'
import { ShieldCheckIcon } from 'lucide-react'

import { getShopOptions } from '@/api/gen/@tanstack/react-query.gen'
import { Item, ItemMedia } from '@/components/ui/item'
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from '@/components/ui/sidebar'
import { cn } from '@/lib/utils'

// A user belongs to one shop, so the block's workspace switcher shows the shop without a menu.

export function AppLogo({ className }: { className?: string }) {
  return (
    <Item
      className={cn(
        'p-0',
        'flex size-8 shrink-0 items-center justify-center bg-primary text-primary-foreground',
        className,
      )}
      aria-hidden="true"
    >
      <ItemMedia variant="icon" className="size-auto">
        <ShieldCheckIcon className="size-4" />
      </ItemMedia>
    </Item>
  )
}

function SidebarLogo({ className }: { className?: string }) {
  return (
    <span className={cn('relative flex size-6 shrink-0 items-center justify-center', className)}>
      <AppLogo className="absolute top-1/2 left-1/2 origin-center -translate-x-1/2 -translate-y-1/2 scale-75" />
    </span>
  )
}

export function WorkspaceSwitcher() {
  const { data: shop } = useQuery(getShopOptions())

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <SidebarMenuButton className="h-9" tooltip={shop?.name ?? 'COD Guard'}>
          <SidebarLogo className="transition-[margin] duration-300 ease-in-out in-data-[state=collapsed]:-ml-1" />
          <div className="grid min-w-0 leading-tight">
            <span className="truncate font-semibold">{shop?.name ?? 'COD Guard'}</span>
            {shop && <span className="truncate text-xs text-muted-foreground">COD Guard</span>}
          </div>
        </SidebarMenuButton>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
