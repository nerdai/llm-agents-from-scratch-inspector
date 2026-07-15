import { useMutation } from '@tanstack/react-query'
import { type ApiError, editResult } from '../client'
import type { EditResultResponse } from '../types'

export interface EditResultVariables {
  sessionId: string
  content: string
}

/**
 * `PATCH /api/sessions/{id}/result` -- edit the last `TaskStepResult`'s
 * content. Backend requires `need === "next"` and an editable result
 * to exist (409 otherwise, see the route's docstring); `need` is
 * unchanged by a successful edit.
 */
export function useEditResult() {
  return useMutation<EditResultResponse, ApiError, EditResultVariables>({
    mutationFn: ({ sessionId, content }) => editResult(sessionId, { content }),
  })
}
