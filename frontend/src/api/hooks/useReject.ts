import { useMutation } from '@tanstack/react-query'
import { type ApiError, rejectSession } from '../client'
import type { RejectResponse } from '../types'

export interface RejectVariables {
  sessionId: string
  feedback: string
}

/**
 * `POST /api/sessions/{id}/reject` -- reject the session's pending
 * `TaskResult` with operator feedback. Backend requires
 * `need === "approve"` (409 otherwise, see the route's docstring);
 * resolves to `need: "next"` so the loop can continue.
 */
export function useReject() {
  return useMutation<RejectResponse, ApiError, RejectVariables>({
    mutationFn: ({ sessionId, feedback }) =>
      rejectSession(sessionId, { feedback }),
  })
}
