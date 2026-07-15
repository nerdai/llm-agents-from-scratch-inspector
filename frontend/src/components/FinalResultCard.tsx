import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import type { Need, TaskResultOut } from '../api/types'

interface FinalResultCardProps {
  result: TaskResultOut
  need: Need | null
  busy: boolean
  completedResult: TaskResultOut | null
  onApprove: () => void
}

function FinalResultCard({
  result,
  need,
  busy,
  completedResult,
  onApprove,
}: FinalResultCardProps) {
  const isDone = completedResult !== null
  const canApprove = need === 'approve' && !busy && !isDone

  return (
    <Card className="border-l-2 border-l-primary">
      <CardHeader className="flex-row items-center gap-2.5 border-b pb-3 text-xs">
        <Badge>TaskResult</Badge>
        {isDone && (
          <Badge variant="outline" className="ml-auto text-primary">
            resolved
          </Badge>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-2.5">
        <p className="text-[15px]">
          {isDone ? completedResult.content : result.content}
        </p>
        {!isDone && (
          <Button
            type="button"
            disabled={!canApprove}
            onClick={onApprove}
            className="self-start"
          >
            {busy ? 'Completing…' : 'Approve'}
          </Button>
        )}
      </CardContent>
    </Card>
  )
}

export default FinalResultCard
