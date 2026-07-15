import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { Need } from '../api/types'
import RolloutDrawer from './RolloutDrawer'

interface ControlsProps {
  need: Need | null
  busy: boolean
  sessionId: string | null
  onGetNextStep: () => void
  onRunStep: () => void
}

const PHASE_LABEL: Record<Need, string> = {
  next: 'Awaiting get_next_step()',
  run: 'Awaiting run_step(step)',
  approve: 'Awaiting approval — complete the task',
  done: 'Task complete',
}

function Controls({
  need,
  busy,
  sessionId,
  onGetNextStep,
  onRunStep,
}: ControlsProps) {
  const canNext = need === 'next' && !busy
  const canRun = need === 'run' && !busy

  return (
    <div className="flex flex-wrap items-center gap-3.5">
      <div className="flex gap-2.5">
        <Button
          type="button"
          variant="secondary"
          disabled={!canNext}
          onClick={onGetNextStep}
          className="font-mono"
        >
          get_next_step()
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={!canRun}
          onClick={onRunStep}
          className="font-mono"
        >
          run_step(step)
        </Button>
      </div>
      <RolloutDrawer sessionId={sessionId} />
      <Badge variant="outline" className="font-mono">
        {busy ? 'Calling backend…' : need ? PHASE_LABEL[need] : ''}
      </Badge>
    </div>
  )
}

export default Controls
