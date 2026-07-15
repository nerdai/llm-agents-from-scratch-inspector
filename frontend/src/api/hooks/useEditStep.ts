import { useMutation } from '@tanstack/react-query'
import { type ApiError, editStep } from '../client'
import type { EditStepResponse } from '../types'

export interface EditStepVariables {
  sessionId: string
  instruction: string
}

/**
 * `PATCH /api/sessions/{id}/step` -- edit the session's pending
 * `TaskStep` in place, before it's consumed by `run-step` (#5).
 * Backend requires `need === "run"` (409 otherwise, see the route's
 * docstring); `need` is unchanged by a successful edit.
 */
export function useEditStep() {
  return useMutation<EditStepResponse, ApiError, EditStepVariables>({
    mutationFn: ({ sessionId, instruction }) =>
      editStep(sessionId, { instruction }),
  })
}
