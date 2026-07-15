import { useMutation } from '@tanstack/react-query'
import { type ApiError, fetchNextStep } from '../client'
import type { NextStepResponse } from '../types'

/**
 * `POST /api/sessions/{id}/next-step` -- advance to the next
 * `TaskStep` or the task's final result.
 *
 * Backend requires `need === "next"` (409 otherwise, see the route's
 * docstring) -- the reducer/UI should gate the call on that, this
 * hook doesn't re-check it.
 */
export function useNextStep() {
  return useMutation<NextStepResponse, ApiError, string>({
    mutationFn: fetchNextStep,
  })
}
