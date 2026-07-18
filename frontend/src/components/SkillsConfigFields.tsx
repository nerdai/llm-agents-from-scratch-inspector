import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import type { SkillScope } from '../api/types'
import type { SkillsConfig } from './useSkillsConfig'

const SCOPE_OPTIONS: readonly SkillScope[] = ['user', 'project']

interface SkillsConfigFieldsProps extends SkillsConfig {
  disabled: boolean
}

/**
 * The Skills Scope + Explicit-only Skills controls -- rendered by
 * `TaskForm` (pre-session) and by `ConfigRail`'s post-completion view
 * (#88), both driven by the same `useSkillsConfig()` instance so a
 * choice made while looking at a just-finished session survives into
 * the next one instead of being discarded the moment "Start new
 * session" resets everything else.
 */
function SkillsConfigFields({
  scopes,
  toggleScope,
  explicitSkills,
  tagDraft,
  setTagDraft,
  commitTag,
  removeTag,
  handleTagKeyDown,
  disabled,
}: SkillsConfigFieldsProps) {
  return (
    <>
      <div className="flex flex-col gap-1.5">
        <span className="text-[10.5px] font-semibold tracking-wide text-muted-foreground uppercase">
          Skills scope
        </span>
        <div className="flex gap-1.5">
          {SCOPE_OPTIONS.map((scope) => {
            const active = scopes.includes(scope)
            return (
              <button
                key={scope}
                type="button"
                disabled={disabled}
                onClick={() => toggleScope(scope)}
                aria-pressed={active}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 font-mono text-[11px] font-semibold tracking-wide uppercase transition-colors',
                  active
                    ? 'border-primary/45 bg-primary/10 text-primary'
                    : 'border-border bg-transparent text-muted-foreground hover:border-foreground/20',
                  disabled && 'pointer-events-none opacity-50',
                )}
              >
                <span
                  className={cn(
                    'size-1.5 rounded-full',
                    active ? 'bg-primary' : 'bg-muted-foreground/40',
                  )}
                />
                {scope}
              </button>
            )
          })}
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
    </>
  )
}

export default SkillsConfigFields
