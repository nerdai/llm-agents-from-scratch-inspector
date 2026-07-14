import type { Need } from '../api/types'

interface ControlsProps {
  need: Need | null
  loading: boolean
  onGetNextStep: () => void
  onRunStep: () => void
}

const PHASE_LABEL: Record<Need, string> = {
  next: 'Awaiting get_next_step()',
  run: 'Awaiting run_step(step)',
  approve: 'Awaiting approval — complete the task',
  done: 'Task complete',
}

function Controls({ need, loading, onGetNextStep, onRunStep }: ControlsProps) {
  const canNext = need === 'next' && !loading
  const canRun = need === 'run' && !loading

  return (
    <div className="controls">
      <div className="controls-buttons">
        <button
          type="button"
          className="btn btn-overseer"
          disabled={!canNext}
          onClick={onGetNextStep}
        >
          get_next_step()
        </button>
        <button
          type="button"
          className="btn btn-worker"
          disabled={!canRun}
          onClick={onRunStep}
        >
          run_step(step)
        </button>
      </div>
      <span className={`phase-pill phase-${need ?? 'next'}`}>
        {loading ? 'Calling backend…' : need ? PHASE_LABEL[need] : ''}
      </span>
    </div>
  )
}

export default Controls
