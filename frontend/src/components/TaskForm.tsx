import { useState } from 'react'
import type { FormEvent } from 'react'
import type { CreateSessionRequest } from '../api/types'

interface TaskFormProps {
  onCreate: (req: CreateSessionRequest) => void
  disabled: boolean
}

// M1 hardcodes the one function tool the prototype exercises
// (Hailstone's `next_number`); a skills/MCP config UI is M2's job.
const DEFAULT_FUNCTION_TOOLS = ['next_number']

function TaskForm({ onCreate, disabled }: TaskFormProps) {
  const [task, setTask] = useState(
    'Compute the full Hailstone sequence starting from 4, step by step using next_number, until you reach 1.',
  )
  const [model, setModel] = useState('')
  const [think, setThink] = useState(false)

  const canSubmit = task.trim().length > 0 && !disabled

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!canSubmit) return
    const req: CreateSessionRequest = {
      task: task.trim(),
      function_tools: DEFAULT_FUNCTION_TOOLS,
    }
    if (model.trim()) req.model = model.trim()
    if (think) req.think = true
    onCreate(req)
  }

  return (
    <form className="task-form" onSubmit={handleSubmit}>
      <label className="field" htmlFor="task-input">
        <span className="field-label">Task instruction</span>
        <textarea
          id="task-input"
          value={task}
          onChange={(e) => setTask(e.target.value)}
          rows={3}
          disabled={disabled}
          required
        />
      </label>

      <div className="field-row">
        <label className="field" htmlFor="model-input">
          <span className="field-label">Model (optional)</span>
          <input
            id="model-input"
            type="text"
            placeholder="server default"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            disabled={disabled}
          />
        </label>

        <label className="field field-checkbox" htmlFor="think-input">
          <input
            id="think-input"
            type="checkbox"
            checked={think}
            onChange={(e) => setThink(e.target.checked)}
            disabled={disabled}
          />
          <span className="field-label">think</span>
        </label>
      </div>

      <p className="field-hint">
        Tools for this session: <code>next_number</code>
      </p>

      <button type="submit" className="btn btn-primary" disabled={!canSubmit}>
        {disabled ? 'Starting…' : 'Create session'}
      </button>
    </form>
  )
}

export default TaskForm
