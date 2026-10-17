import { CheckIcon, XIcon } from 'lucide-react'

import {
  Stepper,
  StepperIndicator,
  StepperItem,
  StepperNav,
  StepperSeparator,
  StepperTitle,
} from '@/components/reui/stepper'
import { cn } from '@/lib/utils'

// A read-only progress line, ReUI c-stepper-29 (compact inline progress): done steps checked, the
// step in progress on a spinning ring (or crossed out when it failed), the rest on dashed rings.

export type ProgressStage = { title: string; state: 'done' | 'current' | 'waiting' | 'todo' | 'failed' }

function DashedRing({ spin = false }: { spin?: boolean }) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
      className={cn('size-4', spin && 'motion-safe:animate-spin')}
    >
      <circle
        cx="8"
        cy="8"
        r="4.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeDasharray="3 1"
        pathLength={28}
      />
    </svg>
  )
}

const INDICATORS = {
  completed: <CheckIcon className="size-2.5 stroke-[3.36]" aria-hidden="true" />,
  inactive: <DashedRing />,
  loading: <DashedRing spin />,
}

/** The stepper itself, for any list of stages (the buyer's page has its own). */
export function ProgressSteps({ stages, label }: { stages: ProgressStage[]; label: string }) {
  const firstOpen = stages.findIndex((s) => s.state !== 'done')
  const value = firstOpen === -1 ? stages.length + 1 : firstOpen + 1

  return (
    <Stepper value={value} indicators={INDICATORS} aria-label={label}>
      <div className="@container -mx-1 -my-2 overflow-x-auto p-2">
        <StepperNav className="min-w-max gap-1">
          {stages.map((stage, index) => {
            const step = index + 1
            const failed = stage.state === 'failed'
            return (
              <StepperItem
                key={stage.title}
                step={step}
                loading={stage.state === 'waiting'}
                className="gap-1.5"
              >
                <span className="inline-flex items-center gap-1.5">
                  <StepperIndicator
                    className={cn(
                      'size-4 bg-ring/20 text-ring/50 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=completed]:bg-primary data-[state=completed]:text-primary-foreground',
                      stage.state === 'waiting' &&
                        'data-[state=active]:bg-transparent data-[state=active]:text-primary',
                      failed && 'data-[state=active]:bg-destructive data-[state=active]:text-white',
                    )}
                  >
                    {failed ? (
                      <XIcon className="size-2.5 stroke-[3.36]" aria-hidden="true" />
                    ) : (
                      <DashedRing />
                    )}
                  </StepperIndicator>
                  <StepperTitle
                    className={cn(
                      'whitespace-nowrap data-[state=inactive]:text-muted-foreground',
                      failed && 'text-destructive',
                    )}
                  >
                    {stage.title}
                  </StepperTitle>
                  {stage.state === 'done' && <span className="sr-only">, done</span>}
                </span>
                {step < stages.length && (
                  <StepperSeparator className="m-0 min-w-6 bg-transparent bg-linear-to-r from-primary to-ring/20 data-[state=completed]:to-primary data-[state=inactive]:from-ring/20 rtl:bg-linear-to-l" />
                )}
              </StepperItem>
            )
          })}
        </StepperNav>
      </div>
    </Stepper>
  )
}
