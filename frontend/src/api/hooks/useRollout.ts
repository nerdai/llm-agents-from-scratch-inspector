import { useQuery } from '@tanstack/react-query'
import { fetchRollout } from '../client'
import { queryKeys } from '../queryKeys'

/**
 * `GET /api/sessions/{id}/rollout` -- a session's full rollout text.
 * Disabled until a `sessionId` exists.
 */
export function useRollout(sessionId: string | null) {
  return useQuery({
    queryKey: queryKeys.sessionRollout(sessionId ?? ''),
    queryFn: () => fetchRollout(sessionId!),
    enabled: sessionId !== null,
  })
}
