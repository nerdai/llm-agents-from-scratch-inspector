import type { ApiError } from '../api/client'
import type {
  NextStepDecisionOut,
  Need,
  SkillOut,
  TaskOut,
  TaskResultOut,
  TaskStepOut,
  TaskStepResultOut,
  ToolCallTraceOut,
} from '../api/types'

/** A normalized, serializable view of a failed request (see `ApiError`). */
export type ApiErrorInfo = Pick<ApiError, 'status' | 'detail'>

/** One rendered card in the timeline -- either an overseer call
 * (`get_next_step`) or a worker call (`run_step`). */
export type TimelineEntry =
  | {
      kind: 'overseer'
      id: string
      outcome: 'next_step'
      decision: NextStepDecisionOut
      step: TaskStepOut
    }
  | {
      kind: 'overseer'
      id: string
      outcome: 'final_result'
      result: TaskResultOut
    }
  | {
      kind: 'worker'
      id: string
      result: TaskStepResultOut
      toolCalls: ToolCallTraceOut[]
      stepCounter: number
    }

export interface SessionState {
  sessionId: string | null
  task: TaskOut | null
  tools: string[]
  skills: SkillOut[]
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
}

export const initialSessionState: SessionState = {
  sessionId: null,
  task: null,
  tools: [],
  skills: [],
  need: null,
  busy: false,
  timeline: [],
  pendingResult: null,
  completedResult: null,
  error: null,
}
