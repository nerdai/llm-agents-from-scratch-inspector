import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import type { NextStepDecisionOut } from '../api/types'

interface OverseerCardProps {
  n: number
  outcome: 'next_step' | 'final_result'
  decision?: NextStepDecisionOut
  instruction?: string
}

function OverseerCard({
  n,
  outcome,
  decision,
  instruction,
}: OverseerCardProps) {
  return (
    <Card className="border-l-2 border-l-primary">
      <CardHeader className="flex-row items-center gap-2.5 border-b pb-3 text-xs">
        <span className="font-mono font-semibold text-muted-foreground">
          #{n}
        </span>
        <Badge>overseer</Badge>
        <code className="font-mono text-foreground">get_next_step()</code>
      </CardHeader>
      <CardContent className="flex flex-col gap-2.5">
        {decision?.content && (
          <div className="flex flex-col gap-1">
            <span className="text-[10.5px] font-semibold tracking-wide text-muted-foreground uppercase">
              decision
            </span>
            <pre className="rounded-md bg-muted p-2 font-mono text-xs whitespace-pre-wrap">
              {decision.content}
            </pre>
          </div>
        )}
        {outcome === 'next_step' ? (
          <div className="flex flex-col gap-1">
            <span className="text-[10.5px] font-semibold tracking-wide text-muted-foreground uppercase">
              next step
            </span>
            <p className="text-sm font-medium">{instruction}</p>
          </div>
        ) : (
          <p className="text-sm text-primary">
            kind = final_result — task objective reached
          </p>
        )}
      </CardContent>
    </Card>
  )
}

export default OverseerCard
