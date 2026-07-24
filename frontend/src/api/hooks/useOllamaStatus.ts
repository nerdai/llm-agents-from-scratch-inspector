import { useQuery } from '@tanstack/react-query'
import { fetchOllamaStatus } from '../client'
import { queryKeys } from '../queryKeys'

/**
 * `GET /api/ollama/status` -- whether the local Ollama daemon is
 * reachable. Always resolves (never a non-2xx per the route's own
 * docstring), so `data.reachable` -- not query error state -- is what
 * should drive an `ollama serve` hint in the UI.
 *
 * The route always checks the *local* default (`localhost:11434`),
 * regardless of what the discovered agent's LLM is actually
 * configured against -- meaningless for an agent that isn't
 * Ollama-backed, or is but points at a remote/cloud host (see #90).
 * `OllamaStatusChip` only renders the component that calls this hook
 * when `useAgentInfo()` says the agent is (probably) local, so the
 * request only ever fires when it's actually meaningful.
 */
export function useOllamaStatus() {
  return useQuery({
    queryKey: queryKeys.ollamaStatus,
    queryFn: fetchOllamaStatus,
  })
}
