import { useState } from 'react'
import type { FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import type { CreateSessionRequest } from '../api/types'

interface TaskFormProps {
  onCreate: (req: CreateSessionRequest) => void
  disabled: boolean
}

const DEFAULT_TASK =
  'Compute the full Hailstone sequence starting from 4, step by step using next_number, until you reach 1.'

/**
 * `POST /api/sessions`'s only variable field is `task` -- per ADR-002
 * (#47), model/tools/skills/memories are fixed by the
 * `LLMAgentBuilder` the launched script exposes, not sent over HTTP.
 */
function TaskForm({ onCreate, disabled }: TaskFormProps) {
  const [task, setTask] = useState(DEFAULT_TASK)

  const canSubmit = task.trim().length > 0 && !disabled

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!canSubmit) return
    onCreate({ task: task.trim() })
  }

  return (
    <form
      className="flex flex-col gap-3 rounded-lg border p-4"
      onSubmit={handleSubmit}
    >
      <label className="flex flex-col gap-1" htmlFor="task-input">
        <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          Task instruction
        </span>
        <Textarea
          id="task-input"
          value={task}
          onChange={(e) => setTask(e.target.value)}
          rows={3}
          disabled={disabled}
          required
          className="font-mono text-sm"
        />
      </label>

      <Button type="submit" disabled={!canSubmit} className="self-start">
        {disabled ? 'Starting…' : 'Create session'}
      </Button>
    </form>
  )
}

export default TaskForm
