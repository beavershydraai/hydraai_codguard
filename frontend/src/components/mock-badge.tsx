import { DatabaseIcon } from 'lucide-react'

import { Badge } from '@/components/reui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { mockMode } from '@/mocks/fetch'
import { useMockStore } from '@/stores/mock'

/** Tells the viewer which data is simulated: everything (mock mode) or endpoints still at 501. */
export function MockBadge() {
  const mocked = useMockStore((state) => state.mocked)
  if (mockMode === 'off' || (mockMode === 'fallback' && mocked.length === 0)) return null

  return (
    <Tooltip>
      <TooltipTrigger
        render={<Badge variant="warning-light" className="cursor-default gap-1" tabIndex={0} />}
      >
        <DatabaseIcon aria-hidden="true" className="size-3" />
        Sample data
      </TooltipTrigger>
      <TooltipContent side="bottom" align="end" className="max-w-xs">
        {mockMode === 'all' ? (
          <p>All data is simulated (mock); the backend is not called.</p>
        ) : (
          <div className="space-y-1">
            <p>These APIs are not in the backend yet, so they use simulated data:</p>
            <ul className="font-mono text-[11px]">
              {mocked.map((operation) => (
                <li key={operation}>{operation}</li>
              ))}
            </ul>
          </div>
        )}
      </TooltipContent>
    </Tooltip>
  )
}
