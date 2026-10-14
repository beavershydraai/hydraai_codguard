import { cn } from '@/lib/utils'
import {
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  Sidebar as SidebarRoot,
  useSidebar,
} from '@/components/ui/sidebar'

import { NavMain } from './nav-main'
import { NavResources } from './nav-resources'
import { NavSecondary } from './nav-secondary'
import { NavUser } from './nav-user'
import { WorkspaceSwitcher } from './workspace-switcher'

function SidebarRailToggle() {
  const { state, toggleSidebar } = useSidebar()
  const isExpanded = state === 'expanded'

  return (
    <button
      type="button"
      aria-label={isExpanded ? 'Thu gọn thanh bên' : 'Mở rộng thanh bên'}
      onClick={toggleSidebar}
      style={{
        left: isExpanded ? 'var(--sidebar-width)' : 'var(--sidebar-width-icon)',
      }}
      className={cn(
        'group/rail fixed top-1/2 z-30 flex h-12 w-7 -translate-y-1/2 cursor-pointer items-center pl-2 outline-none',
        'transition-[left] duration-200 ease-linear',
      )}
    >
      <span className="flex flex-col items-center">
        {/* Top half - pivots at its bottom (the bar's center) */}
        <span
          aria-hidden="true"
          className={cn(
            'block h-2 w-0.5 rounded-t-full bg-foreground/40',
            'origin-bottom transition-all duration-100 ease-linear',
            isExpanded
              ? 'group-hover/rail:rotate-40 group-hover/rail:bg-foreground/60'
              : 'group-hover/rail:-rotate-40 group-hover/rail:bg-foreground/60',
          )}
        />
        {/* Bottom half - pivots at its top (the bar's center) */}
        <span
          aria-hidden="true"
          className={cn(
            'block h-2 w-0.5 rounded-b-full bg-foreground/40',
            'origin-top transition-all duration-100 ease-linear',
            isExpanded
              ? 'group-hover/rail:-rotate-40 group-hover/rail:bg-foreground/60'
              : 'group-hover/rail:rotate-40 group-hover/rail:bg-foreground/60',
          )}
        />
      </span>

      {/* Label slides in beside the arrow on hover */}
      <span
        className={cn(
          'absolute left-full -ml-2 rounded-md border border-border bg-foreground px-2 py-0.5 text-[11px] font-medium whitespace-nowrap text-background shadow-xs shadow-black/5',
          'pointer-events-none transition-all duration-200 ease-out',
          '-translate-x-0.5 opacity-0',
          'group-hover/rail:translate-x-0 group-hover/rail:opacity-100',
        )}
      >
        {isExpanded ? 'Thu gọn' : 'Mở rộng'}
      </span>
    </button>
  )
}

export function AppSidebar() {
  return (
    <SidebarRoot collapsible="icon">
      <SidebarHeader>
        <WorkspaceSwitcher />
      </SidebarHeader>

      <SidebarContent>
        <NavMain />
        <NavResources />
        <div className="mt-auto">
          <NavSecondary />
        </div>
      </SidebarContent>

      <SidebarFooter className="pb-3">
        <NavUser />
      </SidebarFooter>

      <SidebarRailToggle />
    </SidebarRoot>
  )
}
