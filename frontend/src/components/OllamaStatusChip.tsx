import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { useOllamaStatus } from '../api/hooks'

/**
 * `GET /api/ollama/status` surfaced as a purely informational chip in
 * the app bar. The daemon being unreachable is a common, valid state
 * (the launched agent may run entirely against tools/skills with no
 * live model call yet attempted) -- this must never gate or disable
 * "Create session"; #23 owns any real error surfacing elsewhere.
 */
function OllamaStatusChip() {
  const { data, isPending } = useOllamaStatus()

  const label = isPending
    ? 'checking ollama…'
    : data?.reachable
      ? `ollama ${data.version ?? 'reachable'}`
      : 'ollama offline'

  const dotClassName = isPending
    ? 'bg-muted-foreground'
    : data?.reachable
      ? 'bg-emerald-500'
      : 'bg-amber-500'

  return (
    <Badge
      variant="outline"
      className="gap-1.5 font-mono"
      title="GET /api/ollama/status -- informational only"
    >
      <span className={cn('size-1.5 rounded-full', dotClassName)} />
      {label}
    </Badge>
  )
}

export default OllamaStatusChip
