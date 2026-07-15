import type { ReactNode } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { CreateSessionRequest } from '../api/types'
import type { SessionState } from '../session/types'
import TaskForm from './TaskForm'

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

/**
 * The persistent config sidebar (#21): task input pre-session, then a
 * read-only reflection of what the discovered agent actually has
 * post-session. Rendered by `AppShell`'s `rail` slot -- see that
 * component for the surrounding app-bar/aside/main chrome.
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
        <TaskForm onCreate={onCreate} disabled={state.busy} />
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

      {isDone && (
        <Button type="button" variant="outline" onClick={onReset}>
          Start new session
        </Button>
      )}
    </div>
  )
}

export default ConfigRail
