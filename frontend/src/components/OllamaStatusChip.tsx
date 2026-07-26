import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { useAgentInfo, useOllamaStatus } from '../api/hooks'

/**
 * `GET /api/ollama/status` surfaced as a purely informational chip in
 * the app bar. The daemon being unreachable is a common, valid state
 * (the launched agent may run entirely against tools/skills with no
 * live model call yet attempted) -- this must never gate or disable
 * "Create session"; #23 owns any real error surfacing elsewhere.
 *
 * That route always checks the *local* default (`localhost:11434`),
 * regardless of what the discovered agent's LLM is actually
 * configured against (see #90) -- meaningless, and actively
 * misleading ("ollama offline"), for a script that isn't Ollama-backed
 * at all, or is but points at a remote/cloud host (e.g. Ollama Cloud,
 * `OllamaLLM(host="https://ollama.com", ...)`, authenticated via the
 * `OLLAMA_API_KEY` env var -- see `demo_cloud.py`). `useAgentInfo()`'s
 * `is_local_ollama` distinguishes the three cases; while it's still
 * loading, this defaults to the existing local-check behavior rather
 * than flashing a different state first.
 */
function OllamaStatusChip() {
  const { data: agentInfo } = useAgentInfo()
  const isLocalOllama = agentInfo === undefined || agentInfo.is_local_ollama

  if (!isLocalOllama) {
    const isCloud = agentInfo?.is_local_ollama === false
    return (
      <Badge
        variant="outline"
        className="gap-1.5 font-mono"
        title={
          isCloud
            ? `Agent uses a remote Ollama host (${agentInfo?.ollama_host}) -- no local daemon needed`
            : "Agent's LLM isn't Ollama-backed -- no local daemon needed"
        }
      >
        <span className="size-1.5 rounded-full bg-violet-500" />
        {isCloud ? 'ollama cloud' : 'not ollama'}
      </Badge>
    )
  }

  return <LocalOllamaStatus />
}

/** The original local-daemon reachability check, unchanged -- split
 * out so the query it fires (`useOllamaStatus`) only ever mounts for
 * the local case (see `OllamaStatusChip`'s early return above). */
function LocalOllamaStatus() {
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
