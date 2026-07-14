import type {
  Need,
  RunStepResult,
  TaskInfo,
  TaskResult,
  TaskStep,
  ToolCall,
} from "../api/types";

/** One rendered card in the timeline -- either an overseer call
 * (`get_next_step`) or a worker call (`run_step`). */
export type TimelineEntry =
  | {
      kind: "overseer";
      id: string;
      outcome: "next_step";
      decision: unknown;
      step: TaskStep;
    }
  | {
      kind: "overseer";
      id: string;
      outcome: "final_result";
      result: TaskResult;
    }
  | {
      kind: "worker";
      id: string;
      result: RunStepResult;
      toolCalls: ToolCall[];
      stepCounter: number;
    };

export interface SessionState {
  sessionId: string | null;
  task: TaskInfo | null;
  tools: string[];
  skills: string[];
  need: Need | null;
  timeline: TimelineEntry[];
  finalResult: TaskResult | null;
  completedResult: TaskResult | null;
  loading: boolean;
  error: string | null;
}

export const initialSessionState: SessionState = {
  sessionId: null,
  task: null,
  tools: [],
  skills: [],
  need: null,
  timeline: [],
  finalResult: null,
  completedResult: null,
  loading: false,
  error: null,
};
