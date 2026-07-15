import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import type { Need, SessionConfigOut, ToolCallTraceOut } from '../api/types'

interface RehydratedSessionViewProps {
  rollout: string
  toolCallHistory: ToolCallTraceOut[]
  stepCounter: number
  config: SessionConfigOut | null
  need: Need | null
}

function formatArgs(args: Record<string, unknown>): string {
  try {
    return JSON.stringify(args)
  } catch {
    return String(args)
  }
}

function formatContent(content: unknown): string {
  if (typeof content === 'string') return content
  try {
    return JSON.stringify(content)
  } catch {
    return String(content)
  }
}

/**
 * Rendered once a page reload restores a session from
 * `GET /api/sessions/{id}` (#24).
 *
 * `SessionStateResponse` doesn't give back the same structured,
 * per-operation `TimelineEntry[]` a live session accumulates in
 * `session/reducer.ts` -- only a single whole-conversation `rollout`
 * string and a flat `tool_call_history` not grouped per step. Rather
 * than heuristically re-parsing `rollout`'s prompt-template formatting
 * back into fake step-by-step cards (fragile, and coupled to a
 * formatting convention that isn't a stable API contract -- see this
 * PR's description), this renders exactly what the backend actually
 * hands back. Any *new* get_next_step()/run_step() calls made after
 * this reload accumulate as normal, structured `TimelineEntry` cards
 * in `Timeline` below.
 */
function RehydratedSessionView({
  rollout,
  toolCallHistory,
  stepCounter,
  config,
  need,
}: RehydratedSessionViewProps) {
  return (
    <Card className="border-l-2 border-l-muted-foreground">
      <CardHeader className="flex-row items-center gap-2.5 border-b pb-3 text-xs">
        <Badge variant="outline">rehydrated session</Badge>
        <span className="font-mono text-[11px] text-muted-foreground">
          step {stepCounter}
        </span>
        {need && (
          <span className="ml-auto font-mono text-[11px] font-semibold text-muted-foreground">
            need = {need}
          </span>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-xs text-muted-foreground">
          Restored after a page reload — this reflects the backend's raw
          recorded state, not the step-by-step cards below (those only cover
          calls made in this browser tab since reload).
        </p>

        {config && (
          <div className="flex flex-col gap-1">
            <span className="text-[10.5px] font-semibold tracking-wide text-muted-foreground uppercase">
              config
            </span>
            <code className="font-mono text-xs text-muted-foreground">
              tools: {config.tools.join(', ') || '(none)'} · skills:{' '}
              {config.skills.join(', ') || '(none)'} · model:{' '}
              {config.model ?? '(default)'}
            </code>
          </div>
        )}

        <div className="flex flex-col gap-1">
          <span className="text-[10.5px] font-semibold tracking-wide text-muted-foreground uppercase">
            rollout
          </span>
          <pre className="max-h-96 overflow-y-auto rounded-md bg-muted p-2.5 font-mono text-xs whitespace-pre-wrap">
            {rollout || '(empty)'}
          </pre>
        </div>

        {toolCallHistory.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <span className="text-[10.5px] font-semibold tracking-wide text-muted-foreground uppercase">
              tool call history ({toolCallHistory.length})
            </span>
            {toolCallHistory.map((tc, i) => (
              <div
                className={
                  tc.error
                    ? 'rounded-md border border-destructive bg-muted px-2.5 py-2'
                    : 'rounded-md border bg-muted px-2.5 py-2'
                }
                key={`${tc.tool_name}-${i}`}
              >
                <code className="block font-mono text-xs">
                  {tc.tool_name}({formatArgs(tc.args)})
                </code>
                {tc.error ? (
                  <p className="mt-1 text-sm text-destructive">
                    error: {formatContent(tc.content)}
                  </p>
                ) : (
                  <p className="mt-1 text-sm text-muted-foreground">
                    {formatContent(tc.content)}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default RehydratedSessionView
