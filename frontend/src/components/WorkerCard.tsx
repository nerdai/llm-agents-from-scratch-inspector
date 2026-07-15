import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import type { TaskStepResultOut, ToolCallTraceOut } from '../api/types'

interface WorkerCardProps {
  n: number
  result: TaskStepResultOut
  toolCalls: ToolCallTraceOut[]
  stepCounter: number
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

function WorkerCard({ n, result, toolCalls, stepCounter }: WorkerCardProps) {
  return (
    <Card className="border-l-2 border-l-muted-foreground">
      <CardHeader className="flex-row items-center gap-2.5 border-b pb-3 text-xs">
        <span className="font-mono font-semibold text-muted-foreground">
          #{n}
        </span>
        <Badge variant="secondary">worker</Badge>
        <code className="font-mono text-foreground">run_step(step)</code>
        <span className="ml-auto font-mono text-[11px] font-semibold text-muted-foreground">
          step {stepCounter}
        </span>
      </CardHeader>
      <CardContent className="flex flex-col gap-2.5">
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
        <div className="flex flex-col gap-1">
          <span className="text-[10.5px] font-semibold tracking-wide text-muted-foreground uppercase">
            result
          </span>
          <p className="text-sm">{result.content}</p>
        </div>
      </CardContent>
    </Card>
  )
}

export default WorkerCard
