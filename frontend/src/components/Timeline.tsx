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

  return (
    <div className="flex flex-col gap-3.5">
      {entries.map((entry, i) => {
        const n = i + 1
        const isLast = i === lastIndex
        if (entry.kind === 'overseer') {
          // Only the single most-recent `next_step` entry is
          // editable, and only while the backend is still sitting on
          // that pending `TaskStep` (need === 'run') -- matches the
          // PATCH endpoint's own constraint (session.pending_step).
          const editable =
            isLast && entry.outcome === 'next_step' && need === 'run' && !busy
          return (
            <OverseerCard
              key={entry.id}
              n={n}
              outcome={entry.outcome}
              decision={
                entry.outcome === 'next_step' ? entry.decision : undefined
              }
              step={entry.outcome === 'next_step' ? entry.step : undefined}
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
            n={n}
            result={entry.result}
            toolCalls={entry.toolCalls}
            stepCounter={entry.stepCounter}
            editable={editable}
            busy={busy}
            onSaveResult={onEditResult}
          />
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
        />
      )}
    </div>
  )
}

export default Timeline
