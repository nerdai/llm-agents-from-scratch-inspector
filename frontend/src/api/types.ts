/**
 * Types mirroring the Agent Inspector backend's session API contract
 * (see issues #2-#6). Kept intentionally close to the raw JSON shape
 * the FastAPI backend returns so the client layer needs no mapping.
 */

export type Need = "next" | "run" | "approve" | "done";

export interface TaskInfo {
  id_: string;
  instruction: string;
}

export interface TaskStep {
  id_: string;
  task_id: string;
  instruction: string;
}

export interface TaskResult {
  task_id: string;
  content: string;
}

export interface RunStepResult {
  task_step_id: string;
  content: string;
}

export interface ToolCall {
  tool_name: string;
  args: unknown;
  content: string;
  error?: string | null;
}

export interface CreateSessionRequest {
  task: string;
  model?: string;
  think?: boolean;
  function_tools?: string[];
}

export interface CreateSessionResponse {
  session_id: string;
  task: TaskInfo;
  tools: string[];
  skills: string[];
  need: Need;
}

export interface NextStepDecisionResponse {
  kind: "next_step";
  decision: unknown;
  step: TaskStep;
  need: Need;
}

export interface FinalResultDecisionResponse {
  kind: "final_result";
  result: TaskResult;
  need: Need;
}

export type NextStepResponse =
  | NextStepDecisionResponse
  | FinalResultDecisionResponse;

export interface RunStepResponse {
  result: RunStepResult;
  tool_calls: ToolCall[];
  step_counter: number;
  need: Need;
}

export interface CompleteResponse {
  status: "resolved";
  result: TaskResult;
  need: Need;
}
