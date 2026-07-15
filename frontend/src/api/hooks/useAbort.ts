import { useMutation } from '@tanstack/react-query'
import { type ApiError, abortSession } from '../client'
import type { AbortSessionResponse } from '../types'

/**
 * `POST /api/sessions/{id}/abort` -- abort a session's supervised run
 * from any non-terminal `need`. Backend 409s only if the session is
 * already `need === "done"` (see the route's docstring); resolves to
 * `need: "done"`.
 */
export function useAbort() {
  return useMutation<AbortSessionResponse, ApiError, string>({
    mutationFn: abortSession,
  })
}
