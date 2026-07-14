import type { Need, TaskResult } from "../api/types";

interface FinalResultCardProps {
  result: TaskResult;
  need: Need | null;
  loading: boolean;
  completedResult: TaskResult | null;
  onApprove: () => void;
}

function FinalResultCard({
  result,
  need,
  loading,
  completedResult,
  onApprove,
}: FinalResultCardProps) {
  const isDone = completedResult !== null;
  const canApprove = need === "approve" && !loading && !isDone;

  return (
    <article className="call-card call-final">
      <header className="call-header">
        <span className="role-pill role-final">TaskResult</span>
        {isDone && <span className="status-pill status-resolved">resolved</span>}
      </header>
      <div className="call-body">
        <p className="kv-value final-content">
          {isDone ? completedResult.content : result.content}
        </p>
        {!isDone && (
          <button
            type="button"
            className="btn btn-approve"
            disabled={!canApprove}
            onClick={onApprove}
          >
            {loading ? "Completing…" : "Approve"}
          </button>
        )}
      </div>
    </article>
  );
}

export default FinalResultCard;
