import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import {
  useAbort,
  useComplete,
  useCreateSession,
  useEditResult,
  useEditStep,
  useNextStep,
  useReject,
  useRunStep,
  useSessionState,
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

/** The URL query param a session id is read from/written to (#24). No
 * router library: reload/copy-paste/back-forward all work off plain
 * `window.history`/`URLSearchParams`. */
const SESSION_QUERY_PARAM = 'session'

function readSessionIdFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get(SESSION_QUERY_PARAM)
}

function writeSessionIdToUrl(sessionId: string | null): void {
  const url = new URL(window.location.href)
  if (sessionId) {
    url.searchParams.set(SESSION_QUERY_PARAM, sessionId)
  } else {
    url.searchParams.delete(SESSION_QUERY_PARAM)
  }
  // `replaceState`, not `pushState`: this mirrors the reducer's
  // already-current `sessionId`, it doesn't introduce a new user-facing
  // navigation step -- browser back/forward should move between actual
  // page loads, not between every session-id sync.
  window.history.replaceState(null, '', url)
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

  // On-mount rehydration (#24): a `session_id` in the URL is read once
  // (the lazy initializer only runs on first render) and drives
  // `useSessionState` for exactly one request -- `hasRehydratedRef`
  // guards the effect below so a background refetch (e.g. on window
  // refocus) can never re-dispatch and stomp on live session state
  // gathered since.
  const [rehydrateSessionId] = useState<string | null>(() =>
    readSessionIdFromUrl(),
  )
  const rehydrateQuery = useSessionState(rehydrateSessionId)
  const hasRehydratedRef = useRef(false)
  // Nothing left to rehydrate -- either there was no `?session=` param
  // to begin with, or the one attempt above has already resolved
  // (success or failure). Gates the URL-sync effect below so it can't
  // stomp a still-in-flight `?session=` param with the reducer's
  // not-yet-updated `null` `sessionId`.
  const rehydrationSettled =
    rehydrateSessionId === null ||
    rehydrateQuery.isSuccess ||
    rehydrateQuery.isError

  useEffect(() => {
    if (hasRehydratedRef.current) return
    if (rehydrateQuery.isSuccess) {
      hasRehydratedRef.current = true
      dispatch({ type: 'session/rehydrated', payload: rehydrateQuery.data })
    } else if (rehydrateQuery.isError) {
      // Unknown/expired session_id (404) or any other failure -- fail
      // gracefully rather than retrying forever: fall back to the
      // normal "no session yet" state and let the URL-sync effect
      // below drop the stale param.
      hasRehydratedRef.current = true
    }
  }, [rehydrateQuery.isSuccess, rehydrateQuery.isError, rehydrateQuery.data])

  // Keeps the URL's `?session=` param in sync with the live session id
  // -- written whenever a session is created or rehydrated, cleared on
  // reset/abort-to-nothing -- so copying the URL, refreshing, or using
  // the browser's own back/forward lands back in the same session.
  useEffect(() => {
    if (!rehydrationSettled) return
    writeSessionIdToUrl(state.sessionId)
  }, [state.sessionId, rehydrationSettled])

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
    /** `true` while the on-mount rehydration attempt (see above) is
     * still in flight -- lets the UI show a neutral "restoring…" state
     * instead of flashing `TaskForm` before falling back to it. */
    rehydrating: !rehydrationSettled,
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
