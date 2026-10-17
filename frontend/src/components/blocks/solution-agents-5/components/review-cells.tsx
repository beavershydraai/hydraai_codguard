import { ChevronRightIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/** The chevron that opens a group or an order's details (data-grid-grouping-1). */
export function ExpandButton({
  expanded,
  onToggle,
  label,
}: {
  expanded: boolean
  onToggle: () => void
  label: string
}) {
  return (
    <Button
      type="button"
      size="icon-sm"
      variant="ghost"
      aria-label={expanded ? `Collapse ${label}` : `Expand ${label}`}
      aria-expanded={expanded}
      className="size-6 shrink-0 p-0 text-muted-foreground shadow-none hover:text-foreground"
      onClick={(event) => {
        event.stopPropagation()
        onToggle()
      }}
    >
      <ChevronRightIcon
        className={cn('size-3.5 transition-transform duration-150', expanded && 'rotate-90')}
        aria-hidden="true"
      />
    </Button>
  )
}
