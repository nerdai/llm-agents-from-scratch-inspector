/**
 * Types mirroring the Agent Inspector backend's HTTP contract.
 *
 * Kept intentionally close to the raw JSON shape the FastAPI backend
 * returns (see `src/agent_inspector/schemas.py` and
 * `src/agent_inspector/routes/*.py`) so the client layer needs no
 * mapping. Regenerate/update this file by re-reading those two
 * sources directly rather than trusting call sites -- it's the one
 * place allowed to drift from them.
 */

/** The session lifecycle's server-authoritative state (`services/session.py`'s `Need`). */
export type Need = 'next' | 'run' | 'approve' | 'done'

/** Legal `Need` transitions, mirroring `services/session.py`'s `_NEED_TRANSITIONS`. */
export const NEED_TRANSITIONS: Record<Need, readonly Need[]> = {
  next: ['run', 'approve', 'done'],
  run: ['next', 'done'],
  approve: ['done', 'next'],
  done: [],
}

/** A skill's scope of discovery (`llm_agents_from_scratch.data_structures.skill.SkillScope`). */
export type SkillScope = 'project' | 'user'

// --- Framework data structures, surfaced verbatim (see schemas.py's
// `TypeAlias` comments for why these match 1:1 with no wire mapping). ---

export interface TaskOut {
  id_: string
  instruction: string
}

export interface TaskStepOut {
  id_: string
  task_id: string
  instruction: string
}

export interface TaskStepResultOut {
  task_step_id: string
  content: string
}

export interface TaskResultOut {
  task_id: string
  content: string
}

export interface RejectedTaskResultOut {
  failed_result_content: string
  feedback: string
}

export interface SkillOut {
  name: string
  description: string
  scope: SkillScope
  explicit_only: boolean
}

export interface ToolCallTraceOut {
  tool_name: string
  args: Record<string, unknown>
  content: unknown
  error: boolean
}

// --- GET /api/health ---

export interface HealthResponse {
  status: string
}

// --- GET /api/ollama/status ---

export interface OllamaStatusResponse {
  reachable: boolean
  version: string | null
}

// --- POST /api/sessions ---

export interface CreateSessionRequest {
  task: string
  skills_scopes?: SkillScope[] | null
  explicit_only_skills?: string[] | null
}

export interface CreateSessionResponse {
  session_id: string
  task: TaskOut
  tools: string[]
  skills: SkillOut[]
  model: string | null
  need: Need
}

// --- GET /api/sessions/{id} ---

export interface SessionConfigOut {
  tools: string[]
  skills: string[]
  model: string | null
}

export interface SessionStateResponse {
  session_id: string
  need: Need
  step_counter: number
  rollout: string
  tool_call_history: ToolCallTraceOut[]
  config: SessionConfigOut
  final_result: TaskResultOut | null
}

// --- GET /api/sessions/{id}/rollout ---

export interface RolloutResponse {
  rollout: string
}

// --- GET /api/templates (not session-scoped) ---

export interface TemplatesOut {
  system_message: string
  get_next_step: string
  step_rollout_chat_message: string
  step_rollout_content_instruction: string
  step_rollout_content_tool_call_request: string
  run_step_system_message_without_rollout: string
  run_step_system_message: string
  run_step_user_message: string
  skills_catalog: string
  memories: string
  approval_rejection_feedback: string
}

// --- POST /api/sessions/{id}/next-step ---

export interface NextStepDecisionOut {
  kind: 'next_step' | 'final_result'
  content: string
}

export interface NextStepDecisionResponse {
  kind: 'next_step'
  decision: NextStepDecisionOut
  step: TaskStepOut
  need: Need
}

export interface NextStepFinalResponse {
  kind: 'final_result'
  result: TaskResultOut
  need: Need
}

export type NextStepResponse = NextStepDecisionResponse | NextStepFinalResponse

// --- POST /api/sessions/{id}/run-step ---

export interface RunStepResponse {
  result: TaskStepResultOut
  tool_calls: ToolCallTraceOut[]
  step_counter: number
  need: Need
}

// --- PATCH /api/sessions/{id}/step ---

export interface EditStepRequest {
  instruction: string
}

export interface EditStepResponse {
  step: TaskStepOut
  edited: true
  need: Need
}

// --- POST /api/sessions/{id}/complete ---

export interface CompleteResponse {
  status: 'resolved'
  result: TaskResultOut
  need: Need
}

// --- PATCH /api/sessions/{id}/result ---

export interface EditResultRequest {
  content: string
}

export interface EditResultResponse {
  result: TaskStepResultOut
  edited: true
  need: Need
}

// --- POST /api/sessions/{id}/abort ---

export interface AbortSessionResponse {
  status: 'aborted'
  need: 'done'
}

// --- POST /api/sessions/{id}/reject ---

export interface RejectRequest {
  feedback: string
}

export interface RejectResponse {
  rejected: RejectedTaskResultOut
  need: Need
}
