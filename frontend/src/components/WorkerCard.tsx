import type { RunStepResult, ToolCall } from "../api/types";

interface WorkerCardProps {
  n: number;
  result: RunStepResult;
  toolCalls: ToolCall[];
  stepCounter: number;
}

function formatArgs(args: unknown): string {
  if (args === null || args === undefined) return "";
  if (typeof args === "string") return args;
  try {
    return JSON.stringify(args);
  } catch {
    return String(args);
  }
}

function WorkerCard({ n, result, toolCalls, stepCounter }: WorkerCardProps) {
  return (
    <article className="call-card call-worker">
      <header className="call-header">
        <span className="call-index">#{n}</span>
        <span className="role-pill role-worker">worker</span>
        <code className="call-op">run_step(step)</code>
        <span className="step-counter">step {stepCounter}</span>
      </header>
      <div className="call-body">
        {toolCalls.length > 0 && (
          <div className="tool-trace">
            <span className="kv-label">tool calls</span>
            {toolCalls.map((tc, i) => (
              <div
                className={`tool-call${tc.error ? " tool-call-error" : ""}`}
                key={`${tc.tool_name}-${i}`}
              >
                <code className="tool-call-sig">
                  {tc.tool_name}({formatArgs(tc.args)})
                </code>
                {tc.error ? (
                  <p className="tool-call-content tool-call-error-text">
                    error: {tc.error}
                  </p>
                ) : (
                  <p className="tool-call-content">{tc.content}</p>
                )}
              </div>
            ))}
          </div>
        )}
        <div className="kv">
          <span className="kv-label">result</span>
          <p className="kv-value">{result.content}</p>
        </div>
      </div>
    </article>
  );
}

export default WorkerCard;
