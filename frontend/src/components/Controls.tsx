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
import type { Need } from '../api/types'

interface ControlsProps {
  need: Need | null
  busy: boolean
  /** Whether `need === 'done'` was reached via approval (a real
   * `TaskResult` exists) rather than an abort -- distinguishes "Task
   * complete" from "Aborted" in the phase badge below. */
  isCompleted: boolean
  onAbort: () => void
}

const PHASE_LABEL: Record<Need, string> = {
  next: 'Awaiting get_next_step()',
  run: 'Awaiting run_step(step)',
  approve: 'Awaiting approval — complete the task',
  done: 'Task complete',
}

function Controls({ need, busy, isCompleted, onAbort }: ControlsProps) {
  // Mirrors useSession's own abort() gate (`need !== 'done' && !busy`),
  // so the button's enabled state never lies about what a click would
  // actually do.
  const canAbort = need !== null && need !== 'done' && !busy
  const phaseLabel =
    need === null
      ? null
      : need === 'done' && !isCompleted
        ? 'Aborted'
        : PHASE_LABEL[need]

  // `AlertDialogAction` is a bare Button, not `AlertDialogPrimitive.
  // Close` (unlike `AlertDialogCancel`) -- it doesn't dismiss the
  // dialog on its own, so the open state is managed explicitly here,
  // same as `FinalResultCard`'s approve/reject dialogs.
  const [abortOpen, setAbortOpen] = useState(false)

  const handleAbort = () => {
    setAbortOpen(false)
    onAbort()
  }

  return (
    <div className="flex items-center gap-3.5">
      <Badge variant="outline" className="font-mono">
        {busy ? 'Calling backend…' : (phaseLabel ?? '')}
      </Badge>
      <AlertDialog open={abortOpen} onOpenChange={setAbortOpen}>
        <AlertDialogTrigger
          render={
            <Button type="button" variant="destructive" disabled={!canAbort} />
          }
        >
          Abort
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Abort this session?</AlertDialogTitle>
            <AlertDialogDescription>
              Ends the session immediately without a result. This can&apos;t be
              undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={handleAbort}>
              Abort
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

export default Controls
