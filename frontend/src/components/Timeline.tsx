import { useState } from 'react'
import type { ReactNode } from 'react'
import { ChevronRight } from 'lucide-react'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import type { Need, TaskResultOut } from '../api/types'
import type { TimelineEntry } from '../session/types'
import OverseerCard from './OverseerCard'
import WorkerCard from './WorkerCard'
import FinalResultCard from './FinalResultCard'
import PendingOperationCard from './PendingOperationCard'

interface TimelineProps {
  entries: TimelineEntry[]
  pendingResult: TaskResultOut | null
  completedResult: TaskResultOut | null
  need: Need | null
  busy: boolean
  onApprove: () => void
  onReject: (feedback: string) => void
  onEditStep: (instruction: string) => void
  onEditResult: (content: string) => void
}

/** A short, one-line preview of a step's instruction, shown on its
 * collapsed trigger row so collapsing doesn't lose all context. */
function stepPreview(pair: TimelineEntry[]): string | null {
  const overseer = pair.find((entry) => entry.kind === 'overseer')
  if (!overseer || overseer.kind !== 'overseer') return null
  return overseer.outcome === 'next_step'
    ? overseer.step.instruction
    : overseer.result.content
}

function Timeline({
  entries,
  pendingResult,
  completedResult,
  need,
  busy,
  onApprove,
  onReject,
  onEditStep,
  onEditResult,
}: TimelineProps) {
  // The empty state only applies when nothing has happened, nothing
  // is in flight (#22 -- otherwise the very first get_next_step() call
  // would flash "no calls yet" instead of the pending-operation
  // indicator below), and there's no pending result to show (#24 --
  // `pendingResult` can be non-null with empty `entries` right after a
  // rehydrated reload: the backend's `final_result` exists, but the
  // structured `TimelineEntry` cards that produced it don't -- see
  // `RehydratedSessionView`).
  if (entries.length === 0 && !busy && !pendingResult) {
    return (
      <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
        No calls yet — click get_next_step() to begin.
      </p>
    )
  }

  const lastIndex = entries.length - 1

  // get_next_step()/run_step() entries arrive strictly alternating
  // (overseer, worker, overseer, worker, ...) -- the reducer only ever
  // pushes an overseer entry on `next-step/succeeded` and a worker
  // entry on `run-step/succeeded`, in that call order -- except the
  // very last entry, which is a lone, unpaired overseer `final_result`
  // once the loop ends (no `run_step` follows it). Grouping every two
  // consecutive entries under one step number (and the odd one out
  // under its own) mirrors the book's own framing: the pair together
  // forms one step, driven start to finish by the same LLM agent.
  const stepPairs: TimelineEntry[][] = []
  for (let i = 0; i < entries.length; i += 2) {
    stepPairs.push(entries.slice(i, i + 2))
  }

  return (
    <TimelineSteps
      stepPairs={stepPairs}
      lastIndex={lastIndex}
      need={need}
      busy={busy}
      onEditStep={onEditStep}
      onEditResult={onEditResult}
    >
      {busy && !pendingResult && (need === 'next' || need === 'run') && (
        <PendingOperationCard
          role={need === 'next' ? 'overseer' : 'worker'}
          signature={need === 'next' ? 'get_next_step()' : 'run_step(step)'}
        />
      )}
      {pendingResult && (
        <FinalResultCard
          result={pendingResult}
          need={need}
          busy={busy}
          completedResult={completedResult}
          onApprove={onApprove}
          onReject={onReject}
        />
      )}
    </TimelineSteps>
  )
}

interface TimelineStepsProps {
  stepPairs: TimelineEntry[][]
  lastIndex: number
  need: Need | null
  busy: boolean
  onEditStep: (instruction: string) => void
  onEditResult: (content: string) => void
  children?: ReactNode
}

/**
 * Renders each step-pair as a `Collapsible` group, auto-managing which
 * ones are open: only the newest step starts open, and completing it
 * (a new step-pair appearing) collapses whichever was previously
 * newest -- so the timeline stays focused on "what's happening now"
 * without the operator having to manually tidy up older steps. Any
 * step can still be manually expanded/collapsed at any time; a manual
 * toggle is never overridden by the auto-collapse (that only ever
 * touches the *previously*-newest step at the moment a new one
 * appears, not whatever the operator currently has open).
 */
function TimelineSteps({
  stepPairs,
  lastIndex,
  need,
  busy,
  onEditStep,
  onEditResult,
  children,
}: TimelineStepsProps) {
  const [openSteps, setOpenSteps] = useState<Set<number>>(() => new Set([0]))
  // React's documented "adjusting state when a prop changes" pattern
  // (calling setState directly in the render body, guarded by a
  // comparison against a previous-value state) rather than an effect --
  // this repo's lint config flags synchronous setState-in-effect.
  const [knownPairCount, setKnownPairCount] = useState(stepPairs.length)
  if (stepPairs.length !== knownPairCount) {
    const grew = stepPairs.length > knownPairCount
    const previouslyNewest = knownPairCount - 1
    setKnownPairCount(stepPairs.length)
    if (grew) {
      setOpenSteps((prev) => {
        const next = new Set(prev)
        if (previouslyNewest >= 0) next.delete(previouslyNewest)
        next.add(stepPairs.length - 1)
        return next
      })
    }
  }

  const toggleStep = (pairIndex: number) => {
    setOpenSteps((prev) => {
      const next = new Set(prev)
      if (next.has(pairIndex)) next.delete(pairIndex)
      else next.add(pairIndex)
      return next
    })
  }

  return (
    <div className="flex flex-col gap-3">
      {stepPairs.map((pair, pairIndex) => {
        const stepNumber = pairIndex + 1
        const open = openSteps.has(pairIndex)
        const preview = !open ? stepPreview(pair) : null
        return (
          <Collapsible
            key={pair[0].id}
            open={open}
            onOpenChange={() => toggleStep(pairIndex)}
          >
            <CollapsibleTrigger className="group/step flex w-full items-center gap-1.5 rounded-md px-1 py-0.5 text-left hover:bg-muted/50">
              <ChevronRight
                className={cn(
                  'size-3 flex-none text-muted-foreground transition-transform',
                  open && 'rotate-90',
                )}
              />
              <span className="flex-none text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
                Step {stepNumber}
              </span>
              {preview && (
                <span className="truncate text-xs text-muted-foreground">
                  {preview}
                </span>
              )}
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="flex flex-col gap-1.5 pt-1.5">
                {pair.map((entry, offset) => {
                  const i = pairIndex * 2 + offset
                  const isLast = i === lastIndex
                  if (entry.kind === 'overseer') {
                    // Only the single most-recent `next_step` entry is
                    // editable, and only while the backend is still
                    // sitting on that pending `TaskStep` (need === 'run')
                    // -- matches the PATCH endpoint's own constraint
                    // (session.pending_step).
                    const editable =
                      isLast &&
                      entry.outcome === 'next_step' &&
                      need === 'run' &&
                      !busy
                    return (
                      <OverseerCard
                        key={entry.id}
                        n={stepNumber}
                        outcome={entry.outcome}
                        decision={
                          entry.outcome === 'next_step'
                            ? entry.decision
                            : undefined
                        }
                        step={
                          entry.outcome === 'next_step' ? entry.step : undefined
                        }
                        editable={editable}
                        busy={busy}
                        onSaveInstruction={onEditStep}
                      />
                    )
                  }
                  // Same rule for the last `TaskStepResult` (need === 'next').
                  const editable = isLast && need === 'next' && !busy
                  return (
                    <WorkerCard
                      key={entry.id}
                      n={stepNumber}
                      result={entry.result}
                      toolCalls={entry.toolCalls}
                      stepCounter={entry.stepCounter}
                      editable={editable}
                      busy={busy}
                      onSaveResult={onEditResult}
                    />
                  )
                })}
              </div>
            </CollapsibleContent>
          </Collapsible>
        )
      })}
      {children}
    </div>
  )
}

export default Timeline
