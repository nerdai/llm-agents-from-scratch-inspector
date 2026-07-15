import { Loader2 } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import StatusPill from './StatusPill'

interface PendingOperationCardProps {
  role: 'overseer' | 'worker'
  signature: string
}

const ROLE_CLASSES = {
  overseer: {
    border: 'border-l-violet-500/50',
    label: 'text-violet-700 dark:text-violet-300',
  },
  worker: {
    border: 'border-l-amber-500/50',
    label: 'text-amber-700 dark:text-amber-300',
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
function PendingOperationCard({ role, signature }: PendingOperationCardProps) {
  const { border, label } = ROLE_CLASSES[role]

  return (
    <Card
      className={`border-l-[3px] border-dashed py-0 ${border}`}
      data-slot="pending-operation-card"
    >
      <CardContent className="flex items-center gap-2.5 py-3 text-xs">
        <Loader2 className="size-3.5 animate-spin text-muted-foreground" />
        <span
          className={`font-mono text-[11px] font-bold tracking-wide uppercase ${label}`}
        >
          {role}
        </span>
        <code className="font-mono text-muted-foreground">{signature}</code>
        <StatusPill
          tone={role === 'overseer' ? 'violet' : 'amber'}
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
