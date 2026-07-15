import type { Need, TaskResultOut } from '../api/types'
import type { TimelineEntry } from '../session/types'
import OverseerCard from './OverseerCard'
import WorkerCard from './WorkerCard'
import FinalResultCard from './FinalResultCard'

interface TimelineProps {
  entries: TimelineEntry[]
  pendingResult: TaskResultOut | null
  completedResult: TaskResultOut | null
  need: Need | null
  busy: boolean
  onApprove: () => void
}

function Timeline({
  entries,
  pendingResult,
  completedResult,
  need,
  busy,
  onApprove,
}: TimelineProps) {
  // `pendingResult` can be non-null with an empty `entries` right after
  // a rehydrated reload (#24) -- the backend's `final_result` exists,
  // but the structured `TimelineEntry` cards that produced it don't
  // (see `RehydratedSessionView`). Only take the empty-state early
  // return when there's truly nothing to show.
  if (entries.length === 0 && !pendingResult) {
    return (
      <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
        No calls yet — click get_next_step() to begin.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-3.5">
      {entries.map((entry, i) => {
        const n = i + 1
        if (entry.kind === 'overseer') {
          return (
            <OverseerCard
              key={entry.id}
              n={n}
              outcome={entry.outcome}
              decision={
                entry.outcome === 'next_step' ? entry.decision : undefined
              }
              instruction={
                entry.outcome === 'next_step'
                  ? entry.step.instruction
                  : undefined
              }
            />
          )
        }
        return (
          <WorkerCard
            key={entry.id}
            n={n}
            result={entry.result}
            toolCalls={entry.toolCalls}
            stepCounter={entry.stepCounter}
          />
        )
      })}
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
