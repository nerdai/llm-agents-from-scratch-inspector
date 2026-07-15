import { useCallback, useReducer } from 'react'
import {
  useAbort,
  useComplete,
  useCreateSession,
  useEditResult,
  useEditStep,
  useNextStep,
  useReject,
  useRunStep,
} from '../api/hooks'
import type { ApiError } from '../api/client'
import type { CreateSessionRequest } from '../api/types'
import { initialSessionState, type ApiErrorInfo } from './types'
import { sessionReducer } from './reducer'

function isApiError(err: unknown): err is ApiError {
  return (
    typeof err === 'object' &&
    err !== null &&
    'status' in err &&
    'detail' in err
  )
}

function toErrorInfo(err: unknown): ApiErrorInfo {
  if (isApiError(err)) return { status: err.status, detail: err.detail }
  return {
    status: 0,
    detail: err instanceof Error ? err.message : String(err),
  }
}

/**
 * Drives one Agent Inspector session end to end, on top of the
 * `api/hooks/` TanStack Query mutations and the `need`/`busy` reducer
 * (#20). Each imperative method here is a thin "gate on `need`/`busy`,
 * dispatch `busy/start`, call the mutation, dispatch its outcome"
 * wrapper -- the reducer (not this hook) owns what each outcome means
 * for `SessionState`.
 *
 * Exposes one method per mutating endpoint so #21-#24 (config rail,
 * timeline, drawers, rehydration) can build their UI directly on this
 * hook; today's `App.tsx` only wires up the subset it already
 * exercised pre-#20 (`start`/`getNextStep`/`runNextStep`/`approve`).
 */
export function useSession() {
  const [state, dispatch] = useReducer(sessionReducer, initialSessionState)

  const createSessionMutation = useCreateSession()
  const nextStepMutation = useNextStep()
  const runStepMutation = useRunStep()
  const editStepMutation = useEditStep()
  const completeMutation = useComplete()
  const editResultMutation = useEditResult()
  const rejectMutation = useReject()
  const abortMutation = useAbort()

  const start = useCallback(
    async (body: CreateSessionRequest) => {
      dispatch({ type: 'busy/start' })
      try {
        const payload = await createSessionMutation.mutateAsync(body)
        dispatch({ type: 'session/created', payload })
      } catch (err) {
        dispatch({ type: 'busy/error', error: toErrorInfo(err) })
      }
    },
    [createSessionMutation],
  )

  const getNextStep = useCallback(async () => {
    if (!state.sessionId || state.need !== 'next' || state.busy) return
    dispatch({ type: 'busy/start' })
    try {
      const payload = await nextStepMutation.mutateAsync(state.sessionId)
      dispatch({ type: 'next-step/succeeded', payload })
    } catch (err) {
      dispatch({ type: 'busy/error', error: toErrorInfo(err) })
    }
  }, [state.sessionId, state.need, state.busy, nextStepMutation])

  const runNextStep = useCallback(async () => {
    if (!state.sessionId || state.need !== 'run' || state.busy) return
    dispatch({ type: 'busy/start' })
    try {
      const payload = await runStepMutation.mutateAsync(state.sessionId)
      dispatch({ type: 'run-step/succeeded', payload })
    } catch (err) {
      dispatch({ type: 'busy/error', error: toErrorInfo(err) })
    }
  }, [state.sessionId, state.need, state.busy, runStepMutation])

  const editStep = useCallback(
    async (instruction: string) => {
      if (!state.sessionId || state.need !== 'run' || state.busy) return
      dispatch({ type: 'busy/start' })
      try {
        const payload = await editStepMutation.mutateAsync({
          sessionId: state.sessionId,
          instruction,
        })
        dispatch({ type: 'step/edited', payload })
      } catch (err) {
        dispatch({ type: 'busy/error', error: toErrorInfo(err) })
      }
    },
    [state.sessionId, state.need, state.busy, editStepMutation],
  )

  const approve = useCallback(async () => {
    if (!state.sessionId || state.need !== 'approve' || state.busy) return
    dispatch({ type: 'busy/start' })
    try {
      const payload = await completeMutation.mutateAsync(state.sessionId)
      dispatch({ type: 'session/completed', payload })
    } catch (err) {
      dispatch({ type: 'busy/error', error: toErrorInfo(err) })
    }
  }, [state.sessionId, state.need, state.busy, completeMutation])

  const editResult = useCallback(
    async (content: string) => {
      if (!state.sessionId || state.need !== 'next' || state.busy) return
      dispatch({ type: 'busy/start' })
      try {
        const payload = await editResultMutation.mutateAsync({
          sessionId: state.sessionId,
          content,
        })
        dispatch({ type: 'result/edited', payload })
      } catch (err) {
        dispatch({ type: 'busy/error', error: toErrorInfo(err) })
      }
    },
    [state.sessionId, state.need, state.busy, editResultMutation],
  )

  const reject = useCallback(
    async (feedback: string) => {
      if (!state.sessionId || state.need !== 'approve' || state.busy) return
      dispatch({ type: 'busy/start' })
      try {
        const payload = await rejectMutation.mutateAsync({
          sessionId: state.sessionId,
          feedback,
        })
        dispatch({ type: 'session/rejected', payload })
      } catch (err) {
        dispatch({ type: 'busy/error', error: toErrorInfo(err) })
      }
    },
    [state.sessionId, state.need, state.busy, rejectMutation],
  )

  const abort = useCallback(async () => {
    if (!state.sessionId || state.need === 'done' || state.busy) return
    dispatch({ type: 'busy/start' })
    try {
      const payload = await abortMutation.mutateAsync(state.sessionId)
      dispatch({ type: 'session/aborted', payload })
    } catch (err) {
      dispatch({ type: 'busy/error', error: toErrorInfo(err) })
    }
  }, [state.sessionId, state.need, state.busy, abortMutation])

  const reset = useCallback(() => dispatch({ type: 'reset' }), [])

  return {
    state,
    start,
    getNextStep,
    runNextStep,
    editStep,
    approve,
    editResult,
    reject,
    abort,
    reset,
  }
}
