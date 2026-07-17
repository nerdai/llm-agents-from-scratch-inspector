import { useEffect, useRef, useState } from 'react'
import { Cog } from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import type { TaskStepResultOut, ToolCallTraceOut } from '../api/types'
import EditableField from './EditableField'
import StatusPill from './StatusPill'

interface StepResultCardProps {
  result: TaskStepResultOut
  toolCalls: ToolCallTraceOut[]
  stepCounter: number
  /** True exactly when this is the most recent result entry and
   * `need === 'next' && !busy` -- see `Timeline`. */
  editable: boolean
  busy: boolean
  onSaveResult: (content: string) => void
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
 * Client-side, purely cosmetic reveal of `text`: the backend has no
 * token-level streaming (see issue #30, unresolved and out of scope
 * here) -- `run_step`'s response arrives as one complete payload, so
 * this just plays a typewriter effect over the already-arrived text
 * once, on mount. Later changes to `text` (an in-place edit via
 * `EditableField`) are reflected immediately, with no replay.
 */
function useTypewriterReveal(text: string, msPerChar = 6): string {
  const [revealed, setRevealed] = useState('')
  const startedRef = useRef(false)

  useEffect(() => {
    if (startedRef.current) {
      setRevealed(text)
      return
    }
    startedRef.current = true
    let i = 0
    const id = setInterval(() => {
      i += 1
      setRevealed(text.slice(0, i))
      if (i >= text.length) clearInterval(id)
    }, msPerChar)
    return () => clearInterval(id)
  }, [text, msPerChar])

  return revealed
}

/**
 * Domain card for one `run_step(step)` call -- its tool-call trace
 * plus the resulting `TaskStepResult`, editable in place while it's
 * still the pending result the next `get_next_step()` call will see.
 */
function StepResultCard({
  result,
  toolCalls,
  stepCounter,
  editable,
  busy,
  onSaveResult,
}: StepResultCardProps) {
  const revealed = useTypewriterReveal(result.content)
  const isRevealing = revealed.length < result.content.length

  return (
    <Card className="[--card-spacing:--spacing(5)] gap-0 border-l-[3px] border-l-amber-500 py-0">
      <CardHeader className="flex-row items-center gap-2.5 border-b bg-amber-500/5 pt-3 pb-3 text-xs">
        <Cog className="size-3.5 text-amber-600 dark:text-amber-300" />
        <code className="rounded bg-amber-500/10 px-1.5 py-0.5 font-mono text-foreground">
          run_step(step)
        </code>
        <span className="font-mono text-[11px] font-semibold text-muted-foreground">
          step {stepCounter}
        </span>
        <StatusPill tone="amber" className="ml-auto">
          done
        </StatusPill>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 py-3.5">
        {toolCalls.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <span className="text-[10.5px] font-semibold tracking-wide text-muted-foreground uppercase">
              tool calls
            </span>
            {toolCalls.map((tc, i) => (
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
        <EditableField
          label="result"
          value={result.content}
          displayValue={
            <p className="text-sm">
              {revealed}
              {isRevealing && (
                <span className="ml-0.5 inline-block h-3.5 w-[2px] animate-pulse align-middle bg-foreground" />
              )}
            </p>
          }
          editable={editable}
          busy={busy}
          onSave={onSaveResult}
        />
      </CardContent>
    </Card>
  )
}

export default StepResultCard
