import type { Need, TaskResult } from "../api/types";
import type { TimelineEntry } from "../session/types";
import OverseerCard from "./OverseerCard";
import WorkerCard from "./WorkerCard";
import FinalResultCard from "./FinalResultCard";

interface TimelineProps {
  entries: TimelineEntry[];
  finalResult: TaskResult | null;
  completedResult: TaskResult | null;
  need: Need | null;
  loading: boolean;
  onApprove: () => void;
}

function Timeline({
  entries,
  finalResult,
  completedResult,
  need,
  loading,
  onApprove,
}: TimelineProps) {
  if (entries.length === 0) {
    return (
      <p className="timeline-empty">
        No calls yet — click get_next_step() to begin.
      </p>
    );
  }

  return (
    <div className="timeline">
      {entries.map((entry, i) => {
        const n = i + 1;
        if (entry.kind === "overseer") {
          return (
            <OverseerCard
              key={entry.id}
              n={n}
              outcome={entry.outcome}
              decision={entry.outcome === "next_step" ? entry.decision : undefined}
              instruction={
                entry.outcome === "next_step" ? entry.step.instruction : undefined
              }
            />
          );
        }
        return (
          <WorkerCard
            key={entry.id}
            n={n}
            result={entry.result}
            toolCalls={entry.toolCalls}
            stepCounter={entry.stepCounter}
          />
        );
      })}
      {finalResult && (
        <FinalResultCard
          result={finalResult}
          need={need}
          loading={loading}
          completedResult={completedResult}
          onApprove={onApprove}
        />
      )}
    </div>
  );
}

export default Timeline;
