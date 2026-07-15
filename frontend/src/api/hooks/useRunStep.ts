import { useMutation } from '@tanstack/react-query'
import { type ApiError, runStep } from '../client'
import type { RunStepResponse } from '../types'

/**
 * `POST /api/sessions/{id}/run-step` -- execute the session's pending
 * `TaskStep`. Backend requires `need === "run"` (409 otherwise); a
 * framework/LLM failure surfaces as a 502 (see the route's docstring).
 */
export function useRunStep() {
  return useMutation<RunStepResponse, ApiError, string>({
    mutationFn: runStep,
  })
}
