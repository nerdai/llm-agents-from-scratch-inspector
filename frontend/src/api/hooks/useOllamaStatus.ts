import { useQuery } from '@tanstack/react-query'
import { fetchOllamaStatus } from '../client'
import { queryKeys } from '../queryKeys'

/**
 * `GET /api/ollama/status` -- whether the local Ollama daemon is
 * reachable. Always resolves (never a non-2xx per the route's own
 * docstring), so `data.reachable` -- not query error state -- is what
 * should drive an `ollama serve` hint in the UI.
 */
export function useOllamaStatus() {
  return useQuery({
    queryKey: queryKeys.ollamaStatus,
    queryFn: fetchOllamaStatus,
  })
}
