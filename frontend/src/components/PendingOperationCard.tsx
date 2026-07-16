import { Loader2 } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import StatusPill from './StatusPill'

interface PendingOperationCardProps {
  kind: 'decision' | 'result'
  signature: string
}

const KIND_CLASSES = {
  decision: {
    border: 'border-l-violet-500/50',
  },
  result: {
    border: 'border-l-amber-500/50',
  },
} as const

/**
 * A transient, non-timeline row shown only while `SessionState.busy`
 * is true for a `get_next_step()`/`run_step(step)` call. There is no
 * `TimelineEntry` for it -- the reducer only ever appends entries for
 * calls that already resolved (see `session/reducer.ts`) -- so
 * "in-flight" status per #22 is represented here, driven by the
 * shared `busy`/`need` pair, rather than as per-card history.
 */
function PendingOperationCard({ kind, signature }: PendingOperationCardProps) {
  const { border } = KIND_CLASSES[kind]

  return (
    <Card
      className={`border-l-[3px] border-dashed py-0 ${border}`}
      data-slot="pending-operation-card"
    >
      <CardContent className="flex items-center gap-2.5 py-3 text-xs">
        <Loader2 className="size-3.5 animate-spin text-muted-foreground" />
        <code className="font-mono text-muted-foreground">{signature}</code>
        <StatusPill
          tone={kind === 'decision' ? 'violet' : 'amber'}
          pulse
          className="ml-auto"
        >
          in flight
        </StatusPill>
      </CardContent>
    </Card>
  )
}

export default PendingOperationCard
