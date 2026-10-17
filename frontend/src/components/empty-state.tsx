import { Link, type LinkProps } from '@tanstack/react-router'
import { ChevronRightIcon, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { IconStack } from '@/components/reui/icon-stack'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Item, ItemActions, ItemContent, ItemMedia, ItemTitle } from '@/components/ui/item'
import { cn } from '@/lib/utils'

// Empty states adapted from ReUI empty-state-1: an illustration, a title, what to do next as one
// or two buttons, and optional guide links. `icon` swaps the stacked-records illustration for a
// ReUI icon stack, for a list that is empty because the work is done.

export type EmptyGuide = {
  label: string
  icon: LucideIcon
  to: LinkProps['to']
  search?: LinkProps['search']
}

export function EmptyState({
  title,
  description,
  actions,
  guides,
  icon: Icon,
  className,
}: {
  title: string
  description: ReactNode
  actions?: ReactNode
  guides?: EmptyGuide[]
  icon?: LucideIcon
  className?: string
}) {
  return (
    <div className={cn('flex w-full flex-col items-center gap-10 py-10', className)}>
      <Empty className="flex-none gap-6 rounded-none border-0 p-0 md:p-0">
        <EmptyHeader className="max-w-md gap-4">
          <EmptyMedia className="mb-0">
            {Icon ? (
              <IconStack aria-hidden="true">
                <Icon className="size-4" />
              </IconStack>
            ) : (
              <RecordsIllustration />
            )}
          </EmptyMedia>
          <div className="flex flex-col items-center gap-1.5">
            <EmptyTitle className="text-lg font-semibold tracking-tight">{title}</EmptyTitle>
            <EmptyDescription className="max-w-sm text-sm/relaxed">{description}</EmptyDescription>
          </div>
        </EmptyHeader>
        {actions && (
          <EmptyContent className="max-w-none gap-0">
            <div className="flex w-full flex-wrap items-center justify-center gap-2">{actions}</div>
          </EmptyContent>
        )}
      </Empty>
      {guides && guides.length > 0 && (
        <div className="w-full max-w-md space-y-2.5 sm:max-w-lg">
          <p className="text-sm text-muted-foreground">Quick guides</p>
          <div className="grid gap-2.5 sm:grid-cols-2">
            {guides.map(({ label, icon: GuideIcon, to, search }) => (
              <Item
                key={label}
                variant="outline"
                render={<Link to={to} search={search} />}
                className="min-w-0 transition-colors hover:bg-muted/30"
              >
                <ItemMedia className="text-muted-foreground">
                  <GuideIcon className="size-4" aria-hidden="true" />
                </ItemMedia>
                <ItemContent className="min-w-0">
                  <ItemTitle className="truncate">{label}</ItemTitle>
                </ItemContent>
                <ItemActions className="ml-auto text-muted-foreground">
                  <ChevronRightIcon className="size-4" aria-hidden="true" />
                </ItemActions>
              </Item>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/** Stacked record cards, the block's illustration. */
function RecordsIllustration() {
  return (
    <div aria-hidden="true" className="relative isolate h-24 w-52">
      <div className="absolute inset-x-6 top-0 h-6 rounded-t-lg border border-border/50 bg-muted/60 dark:bg-muted/30" />
      <div className="absolute inset-x-3 top-3 h-6 rounded-t-lg border border-border/60 bg-muted/80 dark:bg-muted/50" />
      <div className="absolute inset-x-0 top-6 flex h-16 items-center gap-3 rounded-lg border border-border bg-background px-4 shadow-sm">
        <div className="size-8 shrink-0 rounded bg-muted" />
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <div className="h-2.5 w-3/4 rounded bg-muted" />
          <div className="h-2 w-1/2 rounded bg-muted/60" />
        </div>
      </div>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-8 bg-linear-to-b from-background/0 via-background/60 to-background" />
    </div>
  )
}
