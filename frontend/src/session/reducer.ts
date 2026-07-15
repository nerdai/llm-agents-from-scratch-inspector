import { NEED_TRANSITIONS } from '../api/types'
import type {
  AbortSessionResponse,
  CompleteResponse,
  CreateSessionResponse,
  EditResultResponse,
  EditStepResponse,
  Need,
  NextStepResponse,
  RejectResponse,
  RunStepResponse,
} from '../api/types'
import {
  type ApiErrorInfo,
  initialSessionState,
  type SessionState,
} from './types'

/**
 * The `need`/`busy` state machine driving control enablement (#20).
 *
 * A plain `useReducer` rather than XState: the backend is already the
 * source of truth for legal `need` transitions (`_NEED_TRANSITIONS` in
 * `services/session.py`, mirrored here as `NEED_TRANSITIONS` in
 * `api/types.ts`, enforced with a 409 on the wrong `need`) -- this
 * reducer's job is just to reflect that state and the in-flight
 * `busy` flag client-side, not to independently police it. One action
 * per mutating endpoint (plus the shared `busy/start`/`busy/error`
 * pair), matching `api/hooks/`'s one-hook-per-endpoint layout.
 */
export type Action =
  | { type: 'busy/start' }
  | { type: 'busy/error'; error: ApiErrorInfo }
  | { type: 'session/created'; payload: CreateSessionResponse }
  | { type: 'next-step/succeeded'; payload: NextStepResponse }
  | { type: 'run-step/succeeded'; payload: RunStepResponse }
  | { type: 'step/edited'; payload: EditStepResponse }
  | { type: 'result/edited'; payload: EditResultResponse }
  | { type: 'session/completed'; payload: CompleteResponse }
  | { type: 'session/rejected'; payload: RejectResponse }
  | { type: 'session/aborted'; payload: AbortSessionResponse }
  | { type: 'reset' }

function nextEntryId(
  prefix: string,
  timeline: SessionState['timeline'],
): string {
  return `${prefix}-${timeline.length + 1}`
}

/** Dev-time sanity check that a server-reported `need` is one
 * `NEED_TRANSITIONS` actually allows from the client's last-known
 * `need`. A mismatch means the client and server have drifted out of
 * sync with each other (or with each other's copy of the state
 * machine) -- worth a loud warning, not worth crashing the UI over. */
function warnOnIllegalTransition(from: Need | null, to: Need): void {
  if (from === null || from === to) return
  const allowed = NEED_TRANSITIONS[from]
  if (!allowed.includes(to)) {
    console.warn(
      `Illegal need transition reported by backend: ${from} -> ${to} ` +
        `(expected one of [${allowed.join(', ')}])`,
    )
  }
}

export function sessionReducer(
  state: SessionState,
  action: Action,
): SessionState {
  switch (action.type) {
    case 'busy/start':
      return { ...state, busy: true, error: null }

    case 'busy/error':
      return { ...state, busy: false, error: action.error }

    case 'session/created': {
      const res = action.payload
      return {
        ...initialSessionState,
        sessionId: res.session_id,
        task: res.task,
        tools: res.tools,
        skills: res.skills,
        need: res.need,
      }
    }

    case 'next-step/succeeded': {
      const res = action.payload
      warnOnIllegalTransition(state.need, res.need)
      if (res.kind === 'next_step') {
        return {
          ...state,
          busy: false,
          need: res.need,
          timeline: [
            ...state.timeline,
            {
              kind: 'overseer',
              id: nextEntryId('overseer', state.timeline),
              outcome: 'next_step',
              decision: res.decision,
              step: res.step,
            },
          ],
        }
      }
      return {
        ...state,
        busy: false,
        need: res.need,
        pendingResult: res.result,
        timeline: [
          ...state.timeline,
          {
            kind: 'overseer',
            id: nextEntryId('overseer', state.timeline),
            outcome: 'final_result',
            result: res.result,
          },
        ],
      }
    }

    case 'run-step/succeeded': {
      const res = action.payload
      warnOnIllegalTransition(state.need, res.need)
      return {
        ...state,
        busy: false,
        need: res.need,
        timeline: [
          ...state.timeline,
          {
            kind: 'worker',
            id: nextEntryId('worker', state.timeline),
            result: res.result,
            toolCalls: res.tool_calls,
            stepCounter: res.step_counter,
          },
        ],
      }
    }

    case 'step/edited': {
      // Edits the pending `TaskStep` in place (need === "run" both
      // before and after) -- reflect it on the timeline entry that
      // introduced that step, which is always the most recent one.
      const res = action.payload
      warnOnIllegalTransition(state.need, res.need)
      const lastIndex = state.timeline.length - 1
      const timeline = state.timeline.map((entry, i) =>
        i === lastIndex &&
        entry.kind === 'overseer' &&
        entry.outcome === 'next_step'
          ? { ...entry, step: res.step }
          : entry,
      )
      return { ...state, busy: false, need: res.need, timeline }
    }

    case 'result/edited': {
      // Edits the last `TaskStepResult`'s content in place
      // (need === "next" both before and after).
      const res = action.payload
      warnOnIllegalTransition(state.need, res.need)
      const lastIndex = state.timeline.length - 1
      const timeline = state.timeline.map((entry, i) =>
        i === lastIndex && entry.kind === 'worker'
          ? { ...entry, result: res.result }
          : entry,
      )
      return { ...state, busy: false, need: res.need, timeline }
    }

    case 'session/completed': {
      // `pendingResult` is deliberately *not* cleared here: the UI
      // keeps rendering the same `TaskResult` card, just marked
      // resolved via `completedResult` being non-null (see
      // `FinalResultCard`) -- there's no next `TaskResult` coming for
      // this session (`need` is now terminal), so nothing will ever
      // overwrite it either.
      const res = action.payload
      warnOnIllegalTransition(state.need, res.need)
      return {
        ...state,
        busy: false,
        need: res.need,
        completedResult: res.result,
      }
    }

    case 'session/rejected': {
      // Rejection routes back to need === "next" without consulting
      // the LLM (RejectedTaskResult) -- the pending result it was
      // rejecting is gone; #23 owns rendering the feedback itself.
      const res = action.payload
      warnOnIllegalTransition(state.need, res.need)
      return { ...state, busy: false, need: res.need, pendingResult: null }
    }

    case 'session/aborted': {
      const res = action.payload
      warnOnIllegalTransition(state.need, res.need)
      return { ...state, busy: false, need: res.need }
    }

    case 'reset':
      return initialSessionState

    default:
      return state
  }
}
