import { useMutation } from '@tanstack/react-query'
import { type ApiError, createSession } from '../client'
import type { CreateSessionRequest, CreateSessionResponse } from '../types'

/**
 * `POST /api/sessions` -- create a new supervised-run session.
 *
 * Resolves to a `CreateSessionResponse` whose `need` (always `"next"`
 * on success) drives the session reducer's initial state.
 */
export function useCreateSession() {
  return useMutation<CreateSessionResponse, ApiError, CreateSessionRequest>({
    mutationFn: createSession,
  })
}
