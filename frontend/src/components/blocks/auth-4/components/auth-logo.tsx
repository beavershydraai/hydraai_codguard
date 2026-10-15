import { ShieldCheckIcon } from 'lucide-react'

import { Item, ItemMedia } from '@/components/ui/item'
import { cn } from '@/lib/utils'

export function AuthLogo({ className }: { className?: string }) {
  return (
    <Item
      variant="outline"
      className={cn('p-0', 'flex size-8 shrink-0 items-center justify-center text-primary', className)}
      aria-hidden="true"
    >
      <ItemMedia variant="icon" className="size-auto">
        <ShieldCheckIcon className="size-4" />
      </ItemMedia>
    </Item>
  )
}
