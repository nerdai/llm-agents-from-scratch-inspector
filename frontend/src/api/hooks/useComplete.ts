import { useMutation } from '@tanstack/react-query'
import { type ApiError, completeSession } from '../client'
import type { CompleteResponse } from '../types'

/**
 * `POST /api/sessions/{id}/complete` -- approve the session's pending
 * `TaskResult`. Backend requires `need === "approve"` (409 otherwise,
 * see the route's docstring); resolves to `need: "done"`.
 */
export function useComplete() {
  return useMutation<CompleteResponse, ApiError, string>({
    mutationFn: completeSession,
  })
}
