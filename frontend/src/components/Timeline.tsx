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
  // forms one step, which the overseer oversees start to finish.
  const stepPairs: TimelineEntry[][] = []
  for (let i = 0; i < entries.length; i += 2) {
    stepPairs.push(entries.slice(i, i + 2))
  }

  return (
    <div className="flex flex-col gap-5">
      {stepPairs.map((pair, pairIndex) => {
        const stepNumber = pairIndex + 1
        return (
          <div key={pair[0].id} className="flex flex-col gap-1.5">
            <span className="px-1 text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
              Step {stepNumber}
            </span>
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
                      entry.outcome === 'next_step' ? entry.decision : undefined
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
        )
      })}
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
    </div>
  )
}

export default Timeline
