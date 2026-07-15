import { useState } from 'react'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import type { Need, TaskResultOut } from '../api/types'

interface FinalResultCardProps {
  result: TaskResultOut
  need: Need | null
  busy: boolean
  completedResult: TaskResultOut | null
  onApprove: () => void
  onReject: (feedback: string) => void
}

function FinalResultCard({
  result,
  need,
  busy,
  completedResult,
  onApprove,
  onReject,
}: FinalResultCardProps) {
  const isDone = completedResult !== null
  const canDecide = need === 'approve' && !busy && !isDone

  const [approveOpen, setApproveOpen] = useState(false)
  const [rejectOpen, setRejectOpen] = useState(false)
  const [feedback, setFeedback] = useState('')

  const canSubmitReject = feedback.trim().length > 0

  const handleApprove = () => {
    setApproveOpen(false)
    onApprove()
  }

  const handleReject = () => {
    if (!canSubmitReject) return
    onReject(feedback.trim())
    setFeedback('')
    setRejectOpen(false)
  }

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
          <div className="flex gap-2.5">
            <AlertDialog open={approveOpen} onOpenChange={setApproveOpen}>
              <AlertDialogTrigger
                render={<Button type="button" disabled={!canDecide} />}
              >
                {busy ? 'Completing…' : 'Approve'}
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Approve this result?</AlertDialogTitle>
                  <AlertDialogDescription>
                    Marks the task resolved and ends the session. This
                    can&apos;t be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleApprove}>
                    Approve
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>

            <AlertDialog
              open={rejectOpen}
              onOpenChange={(nextOpen: boolean) => {
                setRejectOpen(nextOpen)
                if (!nextOpen) setFeedback('')
              }}
            >
              <AlertDialogTrigger
                render={
                  <Button
                    type="button"
                    variant="outline"
                    disabled={!canDecide}
                  />
                }
              >
                Reject
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Reject this result?</AlertDialogTitle>
                  <AlertDialogDescription>
                    Discards this result. Your feedback goes back to the agent
                    as a RejectedTaskResult on its next get_next_step() call —
                    no LLM call happens right now.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <label
                  className="flex flex-col gap-1"
                  htmlFor="reject-feedback"
                >
                  <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                    Feedback
                  </span>
                  <Textarea
                    id="reject-feedback"
                    value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                    rows={3}
                    placeholder="What should the agent do differently?"
                    required
                    className="font-mono text-sm"
                  />
                </label>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    variant="destructive"
                    disabled={!canSubmitReject}
                    onClick={handleReject}
                  >
                    Reject
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default FinalResultCard
