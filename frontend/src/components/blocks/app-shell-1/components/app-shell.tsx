import { Link, useMatches } from '@tanstack/react-router'
import { Fragment, type ReactNode } from 'react'

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'
// Radix Tooltip needs a TooltipProvider ancestor (Base UI does not); the sidebar
// button tooltips render a Radix Tooltip. This invisible adapter at the block root
// supplies it: a mechanism-only port detail, no design change. (radix port skill)
import { TooltipProvider } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

import { MockBadge } from '@/components/mock-badge'

import { AppSidebar } from './app-sidebar'

/** Breadcrumb trail from the `crumb` in each matched route's staticData. */
function RouteBreadcrumb() {
  const crumbs = useMatches({
    select: (matches) =>
      matches
        .filter((match) => match.staticData.crumb)
        .map((match) => ({ id: match.id, label: match.staticData.crumb!, pathname: match.pathname })),
  })

  return (
    <Breadcrumb>
      <BreadcrumbList>
        {crumbs.map((crumb, index) => {
          const isLast = index === crumbs.length - 1
          return (
            <Fragment key={crumb.id}>
              {index > 0 && <BreadcrumbSeparator className="hidden md:block" />}
              <BreadcrumbItem className={cn(!isLast && 'hidden md:block')}>
                {isLast ? (
                  <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
                ) : (
                  <BreadcrumbLink asChild>
                    <Link to={crumb.pathname}>{crumb.label}</Link>
                  </BreadcrumbLink>
                )}
              </BreadcrumbItem>
            </Fragment>
          )
        })}
      </BreadcrumbList>
    </Breadcrumb>
  )
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <TooltipProvider delayDuration={0}>
      <SidebarProvider
        className={cn(
          '[--sidebar:color-mix(in_oklab,var(--color-sidebar)_60%,transparent)]',
          '[--sidebar-border:transparent]',
          '[--sidebar-width:250px]',
          '[--sidebar-accent:color-mix(in_oklab,var(--color-primary)_5%,transparent)]',
          '[--sidebar-accent-foreground:var(--color-primary)]',
        )}
      >
        {/* Sidebar */}
        <AppSidebar />

        <SidebarInset className="min-w-0">
          <header className="flex h-12 shrink-0 items-center gap-2 transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-12">
            <div className="flex items-center gap-2 px-4">
              <SidebarTrigger className="-ml-1 md:hidden" />
              <RouteBreadcrumb />
            </div>
            <div className="ml-auto px-4">
              <MockBadge />
            </div>
          </header>

          <div className="flex min-w-0 flex-1 flex-col gap-4 p-4 pt-2 md:px-6">{children}</div>
        </SidebarInset>
      </SidebarProvider>
    </TooltipProvider>
  )
}
