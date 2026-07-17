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
import DecisionCard from './DecisionCard'
import StepResultCard from './StepResultCard'
import FinalResultCard from './FinalResultCard'
import PendingOperationCard from './PendingOperationCard'
import StepActionButtons from './StepActionButtons'

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
  onGetNextStep: () => void
  onRunStep: () => void
}

// Shared by every row that can carry the get_next_step()/run_step()
// button column -- the empty-state placeholder, each step-pair, and
// the pending/final-result row -- so the left column reserves the
// same width whether or not it's actually occupied (otherwise a
// step's card visibly narrows/widens as the buttons hop between
// rows). `animate-in`/`fade-in`/`slide-in-from-bottom` (tw-animate-css)
// only plays once per row mount, not on every re-render, since each
// row's key is stable once it exists -- new rows fade in, existing
// ones don't replay it.
const ROW_GRID =
  'grid grid-cols-[9rem_1fr] items-start gap-3 animate-in fade-in slide-in-from-bottom-2 duration-300'

/** A short, one-line preview of a step's instruction, shown on its
 * collapsed trigger row so collapsing doesn't lose all context. */
function stepPreview(pair: TimelineEntry[]): string | null {
  const decisionEntry = pair.find((entry) => entry.kind === 'decision')
  if (!decisionEntry || decisionEntry.kind !== 'decision') return null
  return decisionEntry.outcome === 'next_step'
    ? decisionEntry.step.instruction
    : decisionEntry.result.content
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
  onGetNextStep,
  onRunStep,
}: TimelineProps) {
  // The empty state only applies when nothing has happened, nothing
  // is in flight (#22 -- otherwise the very first get_next_step() call
  // would flash "no calls yet" instead of the pending-operation
  // indicator below), and there's no pending result to show (#24 --
  // `pendingResult` can be non-null with empty `entries` right after a
  // rehydrated reload: the backend's `final_result` exists, but the
  // structured `TimelineEntry` cards that produced it don't -- see
  // `RehydratedSessionView`). It still needs the action buttons, though
  // -- with no step-pairs yet, there's nothing for `TimelineSteps` to
  // hang them on, but a fresh session (need === 'next') or a rehydrated
  // one sitting on `need === 'run'` still needs a way to take the very
  // first in-tab action.
  if (entries.length === 0 && !busy && !pendingResult) {
    const showActions = need === 'next' || need === 'run'
    return (
      <div className={ROW_GRID}>
        <div className="sticky top-3">
          {showActions && (
            <StepActionButtons
              need={need}
              busy={busy}
              onGetNextStep={onGetNextStep}
              onRunStep={onRunStep}
            />
          )}
        </div>
        <p className="min-w-0 rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          {need === 'run'
            ? 'Waiting on run_step(step) for the pending step.'
            : 'No calls yet — click get_next_step() to begin.'}
        </p>
      </div>
    )
  }

  const lastIndex = entries.length - 1

  // get_next_step()/run_step() entries arrive strictly alternating
  // (decision, result, decision, result, ...) -- the reducer only ever
  // pushes a decision entry on `next-step/succeeded` and a result
  // entry on `run-step/succeeded`, in that call order -- except the
  // very last entry, which is a lone, unpaired decision `final_result`
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
      pendingResult={pendingResult}
      onEditStep={onEditStep}
      onEditResult={onEditResult}
      onGetNextStep={onGetNextStep}
      onRunStep={onRunStep}
    >
      {busy && !pendingResult && need === 'next' && (
        <PendingOperationCard kind="decision" signature="get_next_step()" />
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
  pendingResult: TaskResultOut | null
  onEditStep: (instruction: string) => void
  onEditResult: (content: string) => void
  onGetNextStep: () => void
  onRunStep: () => void
  children?: ReactNode
}

/**
 * Renders each step-pair as a `Collapsible` group, auto-managing which
 * ones are open: only the newest step starts open, and starting the
 * next one (get_next_step() going in flight, not waiting for it to
 * resolve -- see `newStepPending` below) collapses whichever was
 * previously newest -- so the timeline stays focused on "what's
 * happening now" without the operator having to manually tidy up
 * older steps. Any step can still be manually expanded/collapsed at
 * any time; a manual toggle is never overridden by the auto-collapse
 * (that only ever touches the *previously*-newest step at the moment
 * a new one begins, not whatever the operator currently has open).
 */
function TimelineSteps({
  stepPairs,
  lastIndex,
  need,
  busy,
  pendingResult,
  onEditStep,
  onEditResult,
  onGetNextStep,
  onRunStep,
  children,
}: TimelineStepsProps) {
  // The button column should only ever move *down*, tracking new
  // content as it accumulates -- never jump back up once a call
  // resolves. A run_step() call is a continuation of the step-pair
  // that's already on screen (its decision half exists, waiting on a
  // result half), so its "in flight" card renders *inside* that same
  // row, right where the real `StepResultCard` will land, rather than
  // in a separate row below -- the button column never has to relocate
  // for that whole cycle. A get_next_step() call, by contrast, has no
  // existing row to attach to (it's about to create a brand new step),
  // so it's the one case that still gets a fresh row below the last
  // complete step -- one deliberate step down, never back up.
  const newStepPending = busy && !pendingResult && need === 'next'
  const hasChildrenRow = newStepPending || pendingResult !== null

  const [openSteps, setOpenSteps] = useState<Set<number>>(() => new Set([0]))
  // React's documented "adjusting state when a prop changes" pattern
  // (calling setState directly in the render body, guarded by a
  // comparison against a previous-value state) rather than an effect --
  // this repo's lint config flags synchronous setState-in-effect.
  const [knownPairCount, setKnownPairCount] = useState(stepPairs.length)
  if (stepPairs.length !== knownPairCount) {
    const grew = stepPairs.length > knownPairCount
    setKnownPairCount(stepPairs.length)
    if (grew) {
      // The newly-real pair opens; collapsing whoever was previously
      // newest already happened below, the moment its get_next_step()
      // call *started* -- not here. Doing it here too (keyed to
      // `stepPairs.length` growth) would shrink that row out from under
      // the button column in the same instant the new row claims it,
      // producing a large, jarring upward jump -- exactly the motion
      // the operator shouldn't see (buttons should only ever move down
      // as content accumulates, never snap back up).
      setOpenSteps((prev) => new Set(prev).add(stepPairs.length - 1))
    }
  }

  // A get_next_step() call in flight means a new step is about to
  // exist -- collapse whichever real pair is currently newest right
  // away, before the new step's row (and the button column) shows up
  // in that exact spot. Collapsing it later, once the call resolves,
  // is what caused the jump described above.
  const [knownNewStepPending, setKnownNewStepPending] = useState(newStepPending)
  if (newStepPending !== knownNewStepPending) {
    setKnownNewStepPending(newStepPending)
    if (newStepPending && stepPairs.length > 0) {
      const currentNewest = stepPairs.length - 1
      setOpenSteps((prev) => {
        const next = new Set(prev)
        next.delete(currentNewest)
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
        const isLastPair = pairIndex === stepPairs.length - 1
        // An incomplete pair (decision half only) whose run_step() call
        // is in flight right now -- see the comment on `newStepPending`
        // above for why this attaches here instead of a separate row.
        const attachPendingResultHere =
          isLastPair &&
          pair.length === 1 &&
          need === 'run' &&
          busy &&
          !pendingResult

        const step = (
          <Collapsible open={open} onOpenChange={() => toggleStep(pairIndex)}>
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
                  if (entry.kind === 'decision') {
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
                      <DecisionCard
                        key={entry.id}
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
                    <StepResultCard
                      key={entry.id}
                      result={entry.result}
                      toolCalls={entry.toolCalls}
                      stepCounter={entry.stepCounter}
                      editable={editable}
                      busy={busy}
                      onSaveResult={onEditResult}
                    />
                  )
                })}
                {attachPendingResultHere && (
                  <PendingOperationCard
                    kind="result"
                    signature="run_step(step)"
                  />
                )}
              </div>
            </CollapsibleContent>
          </Collapsible>
        )

        // The get_next_step()/run_step() pair lives beside whichever
        // step is current, not pinned in a toolbar -- "current" means
        // the newest step-pair while it's still the one being actively
        // driven (need is 'next' or 'run'), and only when a fresh
        // pending-step row isn't about to claim that spot instead (see
        // `newStepPending` above). Once approval/completion takes over
        // (need is 'approve'/'done'), FinalResultCard is the actionable
        // element and no button column is shown here.
        const showActions =
          isLastPair && (need === 'next' || need === 'run') && !newStepPending
        return (
          <div key={pair[0].id} className={ROW_GRID}>
            <div className="sticky top-3">
              {showActions && (
                <StepActionButtons
                  need={need}
                  busy={busy}
                  onGetNextStep={onGetNextStep}
                  onRunStep={onRunStep}
                />
              )}
            </div>
            <div className="min-w-0">{step}</div>
          </div>
        )
      })}
      {hasChildrenRow && (
        <div className={ROW_GRID}>
          <div className="sticky top-3">
            {newStepPending && (
              <StepActionButtons
                need={need}
                busy={busy}
                onGetNextStep={onGetNextStep}
                onRunStep={onRunStep}
              />
            )}
          </div>
          <div className="min-w-0">{children}</div>
        </div>
      )}
    </div>
  )
}

export default Timeline
