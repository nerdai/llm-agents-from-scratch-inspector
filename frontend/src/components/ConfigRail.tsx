import type { ReactNode } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { CreateSessionRequest } from '../api/types'
import type { SessionState } from '../session/types'
import TaskForm from './TaskForm'
import TemplatesSection from './TemplatesSection'

interface ConfigRailProps {
  state: SessionState
  onCreate: (req: CreateSessionRequest) => void
  onReset: () => void
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <span className="text-[10.5px] font-semibold tracking-wide text-muted-foreground uppercase">
      {children}
    </span>
  )
}

/** A group heading one level above `SectionLabel` -- e.g. "LLM Agent"
 * grouping Model/Tools/Skills/Templates -- so nested subsections read
 * as belonging to it rather than sitting as equally-weighted peers. */
function GroupLabel({ children }: { children: ReactNode }) {
  return <span className="text-xs font-bold tracking-tight">{children}</span>
}

/**
 * The persistent config sidebar (#21): task input pre-session, then a
 * read-only reflection of what the discovered agent actually has
 * post-session. Rendered by `AppShell`'s `rail` slot -- see that
 * component for the surrounding app-bar/aside/main chrome.
 *
 * `TemplatesSection` renders in both branches. Templates are actually
 * scoped to the discovered agent, same as tools/model/skills --
 * `LLMAgentBuilder.with_templates(...)` exists in the framework, same
 * fluent shape as `.with_tool(...)` -- but `GET /api/templates`
 * doesn't read the discovered `agent_builder` yet and always returns
 * the framework's hardcoded default (tracked in issue #82), which is
 * why it's rendered without a session the same as with one, same as
 * before this lived in the app bar as `TemplatesDrawer`. In both
 * branches it sits directly above the primary action button ("Create
 * session"/"Start new session" -- passed as `TaskForm`'s `children`
 * pre-session, sibling to the button post-session), so both buttons
 * land in the same spot with the same styling rather than one living
 * mid-form.
 *
 * Deliberately does not own the timeline, the approve/reject gate, or
 * error toasts (#22/#23), and does not rehydrate from a reload (#24).
 */
function ConfigRail({ state, onCreate, onReset }: ConfigRailProps) {
  const hasSession = state.sessionId !== null
  // `need === 'done'` is reached via either approval (`completedResult`
  // set) or abort (`completedResult` stays null) -- "Start new
  // session" should show either way, not just after approval.
  const isDone = state.need === 'done'

  if (!hasSession) {
    return (
      <div className="flex flex-col gap-5 p-4.5">
        <TaskForm onCreate={onCreate} disabled={state.busy}>
          <TemplatesSection />
        </TaskForm>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-5 p-4.5">
      <div className="flex flex-col gap-1.5">
        <SectionLabel>Session</SectionLabel>
        <code className="font-mono text-xs break-all text-muted-foreground">
          {state.sessionId}
        </code>
      </div>

      <div className="flex flex-col gap-1.5">
        <SectionLabel>Task</SectionLabel>
        <p className="text-sm">{state.task?.instruction}</p>
      </div>

      <div className="flex flex-col gap-3.5">
        <GroupLabel>LLM Agent</GroupLabel>

        <div className="flex flex-col gap-1.5">
          <SectionLabel>Model</SectionLabel>
          {state.model ? (
            <Badge variant="outline" className="w-fit font-mono">
              {state.model}
            </Badge>
          ) : (
            <span className="text-xs text-muted-foreground">(unknown)</span>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <SectionLabel>Tools</SectionLabel>
          {state.tools.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {state.tools.map((tool) => (
                <Badge key={tool} variant="outline" className="font-mono">
                  {tool}
                </Badge>
              ))}
            </div>
          ) : (
            <span className="text-xs text-muted-foreground">
              (no tools discovered)
            </span>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <SectionLabel>Skills</SectionLabel>
          {state.skills.length > 0 ? (
            <div className="flex flex-col gap-2">
              {state.skills.map((skill) => (
                <div
                  key={skill.name}
                  className="flex flex-col gap-1 rounded-lg border bg-card p-2.5"
                >
                  <div className="flex flex-wrap items-center gap-1.5">
                    <code className="font-mono text-xs font-semibold">
                      {skill.name}
                    </code>
                    <div className="ml-auto flex gap-1">
                      <Badge variant="secondary">{skill.scope}</Badge>
                      {skill.explicit_only && (
                        <Badge variant="outline">explicit-only</Badge>
                      )}
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {skill.description}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <span className="text-xs text-muted-foreground">
              (no skills discovered)
            </span>
          )}
        </div>

        <TemplatesSection />
      </div>

      {isDone && (
        <Button type="button" onClick={onReset}>
          Start new session
        </Button>
      )}
    </div>
  )
}

export default ConfigRail
