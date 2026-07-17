import { Lightbulb } from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import type { NextStepDecisionOut, TaskStepOut } from '../api/types'
import EditableField from './EditableField'
import StatusPill from './StatusPill'

interface DecisionCardProps {
  outcome: 'next_step' | 'final_result'
  decision?: NextStepDecisionOut
  step?: TaskStepOut
  /** True exactly when this is the most recent `next_step` entry and
   * `need === 'run' && !busy` -- see `Timeline`. */
  editable: boolean
  busy: boolean
  onSaveInstruction: (instruction: string) => void
}

/**
 * Domain card for one `get_next_step()` call -- its reasoning/decision
 * plus (for `next_step` outcomes) the proposed `TaskStep`, editable in
 * place while it's still pending `run_step`.
 */
function DecisionCard({
  outcome,
  decision,
  step,
  editable,
  busy,
  onSaveInstruction,
}: DecisionCardProps) {
  return (
    <Card className="[--card-spacing:--spacing(5)] gap-0 border-l-[3px] border-l-violet-500 py-0">
      <CardHeader className="flex-row items-center gap-2.5 border-b bg-violet-500/5 pt-3 pb-3 text-xs">
        <Lightbulb className="size-3.5 text-violet-600 dark:text-violet-300" />
        <code className="rounded bg-violet-500/10 px-1.5 py-0.5 font-mono text-foreground">
          get_next_step()
        </code>
        {outcome === 'next_step' ? (
          <StatusPill tone="violet" className="ml-auto">
            decided
          </StatusPill>
        ) : (
          <StatusPill tone="emerald" className="ml-auto">
            final result
          </StatusPill>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-3 py-3.5">
        {decision?.content && (
          <div className="flex flex-col gap-1">
            <span className="text-[10.5px] font-semibold tracking-wide text-muted-foreground uppercase">
              reasoning
            </span>
            <pre className="rounded-md bg-muted p-2.5 font-mono text-xs whitespace-pre-wrap text-muted-foreground">
              {decision.content}
            </pre>
          </div>
        )}
        {outcome === 'next_step' && step ? (
          <EditableField
            label="next step"
            value={step.instruction}
            displayValue={
              <p className="text-sm font-medium">{step.instruction}</p>
            }
            editable={editable}
            busy={busy}
            onSave={onSaveInstruction}
          />
        ) : (
          <p className="text-sm text-emerald-700 dark:text-emerald-400">
            kind = final_result — task objective reached
          </p>
        )}
      </CardContent>
    </Card>
  )
}

export default DecisionCard
