import { useQuery } from '@tanstack/react-query'
import { fetchSessionState } from '../client'
import { queryKeys } from '../queryKeys'

/**
 * `GET /api/sessions/{id}` -- full session state for a UI reload
 * (rehydration, see #15). Disabled until a `sessionId` exists.
 */
export function useSessionState(sessionId: string | null) {
  return useQuery({
    queryKey: queryKeys.session(sessionId ?? ''),
    queryFn: () => fetchSessionState(sessionId!),
    enabled: sessionId !== null,
  })
}
