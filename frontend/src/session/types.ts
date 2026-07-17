import type { ApiError } from '../api/client'
import type {
  NextStepDecisionOut,
  Need,
  SessionConfigOut,
  SkillOut,
  TaskOut,
  TaskResultOut,
  TaskStepOut,
  TaskStepResultOut,
  ToolCallTraceOut,
} from '../api/types'

/** A normalized, serializable view of a failed request (see `ApiError`). */
export type ApiErrorInfo = Pick<ApiError, 'status' | 'detail'>

/** One rendered card in the timeline -- either a decision
 * (`get_next_step`) or a result (`run_step`). */
export type TimelineEntry =
  | {
      kind: 'decision'
      id: string
      outcome: 'next_step'
      decision: NextStepDecisionOut
      step: TaskStepOut
    }
  | {
      kind: 'decision'
      id: string
      outcome: 'final_result'
      result: TaskResultOut
    }
  | {
      kind: 'result'
      id: string
      result: TaskStepResultOut
      toolCalls: ToolCallTraceOut[]
    }

export interface SessionState {
  sessionId: string | null
  task: TaskOut | null
  tools: string[]
  skills: SkillOut[]
  /** Best-effort backbone LLM identifier -- `CreateSessionResponse.model`
   * live, or `SessionStateResponse.config.model` on rehydration; `null`
   * whenever the discovered LLM doesn't expose one (see the backend's
   * `SessionConfig.model` docstring). */
  model: string | null
  /** The session lifecycle's server-authoritative state, or `null`
   * before a session exists. */
  need: Need | null
  /** Whether a mutation is currently in flight. */
  busy: boolean
  timeline: TimelineEntry[]
  /** The task's final result, awaiting approval (`need === "approve"`). */
  pendingResult: TaskResultOut | null
  /** The task's final result, once approved (`need === "done"`). */
  completedResult: TaskResultOut | null
  error: ApiErrorInfo | null
  /** `true` once this state came from `GET /api/sessions/{id}` (#24)
   * rather than being built up live from `session/created` onward.
   * `timeline` is *not* reconstructed on rehydration (the backend
   * doesn't persist the structured, per-operation shape it's made of
   * -- only the fields below) -- `rehydrated` lets the UI render an
   * honest summary of what's actually available instead of pretending
   * to have the original step-by-step cards. */
  rehydrated: boolean
  /** The whole-conversation formatted rollout text, present only when
   * `rehydrated` (see `SessionStateResponse.rollout`). */
  rollout: string | null
  /** The flat, not-grouped-by-step tool-call trace from a rehydrated
   * session (see `SessionStateResponse.tool_call_history`). */
  toolCallHistory: ToolCallTraceOut[]
  /** `SessionStateResponse.step_counter` as of rehydration. */
  stepCounter: number
  /** `SessionStateResponse.config`, present only when `rehydrated`. */
  config: SessionConfigOut | null
}

export const initialSessionState: SessionState = {
  sessionId: null,
  task: null,
  tools: [],
  skills: [],
  model: null,
  need: null,
  busy: false,
  timeline: [],
  pendingResult: null,
  completedResult: null,
  error: null,
  rehydrated: false,
  rollout: null,
  toolCallHistory: [],
  stepCounter: 0,
  config: null,
}
