import { useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { CreateSessionRequest, SkillScope } from '../api/types'

interface TaskFormProps {
  onCreate: (req: CreateSessionRequest) => void
  disabled: boolean
}

const DEFAULT_TASK =
  'Compute the full Hailstone sequence starting from 4, step by step using next_number, until you reach 1.'

const SCOPE_OPTIONS: readonly SkillScope[] = ['user', 'project']

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
function TaskForm({ onCreate, disabled }: TaskFormProps) {
  const [task, setTask] = useState(DEFAULT_TASK)
  const [scopes, setScopes] = useState<SkillScope[]>([])
  const [explicitSkills, setExplicitSkills] = useState<string[]>([])
  const [tagDraft, setTagDraft] = useState('')

  const canSubmit = task.trim().length > 0 && !disabled

  const toggleScope = (scope: SkillScope) => {
    setScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope],
    )
  }

  const commitTag = (draft: string) => {
    const name = draft.trim()
    if (!name) return
    setExplicitSkills((prev) => (prev.includes(name) ? prev : [...prev, name]))
    setTagDraft('')
  }

  const removeTag = (name: string) => {
    setExplicitSkills((prev) => prev.filter((s) => s !== name))
  }

  const handleTagKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      commitTag(tagDraft)
    } else if (e.key === 'Backspace' && tagDraft === '') {
      setExplicitSkills((prev) => prev.slice(0, -1))
    }
  }

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!canSubmit) return
    const pending = tagDraft.trim()
    const skills =
      pending && !explicitSkills.includes(pending)
        ? [...explicitSkills, pending]
        : explicitSkills
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

      <div className="flex flex-col gap-1.5">
        <span className="text-[10.5px] font-semibold tracking-wide text-muted-foreground uppercase">
          Skills scope
        </span>
        <div className="flex gap-1.5">
          {SCOPE_OPTIONS.map((scope) => (
            <Button
              key={scope}
              type="button"
              size="sm"
              variant={scopes.includes(scope) ? 'default' : 'outline'}
              disabled={disabled}
              onClick={() => toggleScope(scope)}
              aria-pressed={scopes.includes(scope)}
            >
              {scope}
            </Button>
          ))}
        </div>
        <span className="text-[11px] text-muted-foreground">
          Optional -- omit to use the agent&apos;s default discovery scopes.
        </span>
      </div>

      <label className="flex flex-col gap-1.5" htmlFor="explicit-skills-input">
        <span className="text-[10.5px] font-semibold tracking-wide text-muted-foreground uppercase">
          Explicit-only skills
        </span>
        <div
          className={cn(
            'flex flex-wrap items-center gap-1.5 rounded-lg border border-input px-2 py-1.5',
            disabled && 'opacity-50',
          )}
        >
          {explicitSkills.map((name) => (
            <Badge key={name} variant="secondary" className="font-mono">
              {name}
              <button
                type="button"
                onClick={() => removeTag(name)}
                disabled={disabled}
                aria-label={`Remove ${name}`}
                className="ml-1 leading-none text-muted-foreground hover:text-foreground"
              >
                ×
              </button>
            </Badge>
          ))}
          <Input
            id="explicit-skills-input"
            value={tagDraft}
            onChange={(e) => setTagDraft(e.target.value)}
            onKeyDown={handleTagKeyDown}
            onBlur={() => commitTag(tagDraft)}
            disabled={disabled}
            placeholder={explicitSkills.length === 0 ? 'skill-name…' : ''}
            className="h-6 min-w-20 flex-1 border-none px-1 shadow-none focus-visible:ring-0"
          />
        </div>
        <span className="text-[11px] text-muted-foreground">
          Skill names, by name -- press Enter or comma to add. Hidden from the
          model&apos;s visible catalog, but still invokable by name.
        </span>
      </label>

      <Button type="submit" disabled={!canSubmit}>
        {disabled ? 'Starting…' : 'Create session'}
      </Button>
    </form>
  )
}

export default TaskForm
