import { useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import type { CreateSessionRequest } from '../api/types'
import SkillsConfigFields from './SkillsConfigFields'
import type { SkillsConfig } from './useSkillsConfig'

interface TaskFormProps {
  onCreate: (req: CreateSessionRequest) => void
  disabled: boolean
  /** Pre-fills the task field -- the discovered script's
   * `default_task` (`GET /api/agent-info`, #86) if it set one, or
   * `''` otherwise. Read once, on mount -- `TaskForm` owns `task` as
   * local edit state from then on, same as every other field here. */
  initialTask: string
  /** One `useSkillsConfig()` instance owned by `ConfigRail` (#88) --
   * shared with its post-completion view so a scope/explicit-only
   * choice made while looking at a just-finished session survives
   * into the next one instead of being discarded on "Start new
   * session". */
  skillsConfig: SkillsConfig
  /** Rendered between the form fields and the "Create session" button
   * -- e.g. `TemplatesSection`, so "Create session" stays the very
   * last thing in the rail, matching where "Start new session" sits
   * post-session (see `ConfigRail`). */
  children?: ReactNode
}

/**
 * `POST /api/sessions`'s variable fields are `task`, `skills_scopes`,
 * and `explicit_only_skills` -- per ADR-002 (#47), model/tools/MCP
 * servers are fixed by the `LLMAgentBuilder` the launched script
 * exposes, not sent over HTTP (see the #21 rescope note on the
 * issue). The real skill catalog isn't known until *after* a session
 * exists (`CreateSessionResponse.skills`), so scopes and explicit-only
 * names are blind inputs here: scope toggle chips and a free-text tag
 * list, not a pre-populated picker.
 */
function TaskForm({
  onCreate,
  disabled,
  initialTask,
  skillsConfig,
  children,
}: TaskFormProps) {
  const [task, setTask] = useState(initialTask)
  const { scopes, commitPendingDraft } = skillsConfig

  const canSubmit = task.trim().length > 0 && !disabled

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!canSubmit) return
    const skills = commitPendingDraft()
    onCreate({
      task: task.trim(),
      skills_scopes: scopes.length > 0 ? scopes : undefined,
      explicit_only_skills: skills.length > 0 ? skills : undefined,
    })
  }

  return (
    <form className="flex flex-col gap-5" onSubmit={handleSubmit}>
      <label className="flex flex-col gap-1.5" htmlFor="task-input">
        <span className="text-[10.5px] font-semibold tracking-wide text-muted-foreground uppercase">
          Task
        </span>
        <Textarea
          id="task-input"
          value={task}
          onChange={(e) => setTask(e.target.value)}
          rows={4}
          disabled={disabled}
          required
          placeholder="Describe the goal in plain language…"
          className="text-sm"
        />
        <span className="font-mono text-[11px] text-muted-foreground">
          Task(instruction=…)
        </span>
      </label>

      <SkillsConfigFields {...skillsConfig} disabled={disabled} />

      {children}

      <Button type="submit" disabled={!canSubmit}>
        {disabled ? 'Starting…' : 'Create session'}
      </Button>
    </form>
  )
}

export default TaskForm
