import { Sparkles } from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import type { NextStepDecisionOut, TaskStepOut } from '../api/types'
import EditableField from './EditableField'
import StatusPill from './StatusPill'

interface OverseerCardProps {
  n: number
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
 * Domain card for one `get_next_step()` call -- the overseer's
 * reasoning/decision plus (for `next_step` outcomes) the proposed
 * `TaskStep`, editable in place while it's still pending `run_step`.
 */
function OverseerCard({
  n,
  outcome,
  decision,
  step,
  editable,
  busy,
  onSaveInstruction,
}: OverseerCardProps) {
  return (
    <Card className="gap-0 border-l-[3px] border-l-violet-500 py-0">
      <CardHeader className="flex-row items-center gap-2.5 border-b bg-violet-500/5 pb-3 text-xs">
        <span className="font-mono font-semibold text-muted-foreground">
          #{n}
        </span>
        <span className="inline-flex items-center gap-1 font-mono text-[11px] font-bold tracking-wide text-violet-700 uppercase dark:text-violet-300">
          <Sparkles className="size-3.5" />
          overseer
        </span>
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

export default OverseerCard
