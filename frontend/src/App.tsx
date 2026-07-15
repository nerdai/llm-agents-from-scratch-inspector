import { Button } from '@/components/ui/button'
import TaskForm from './components/TaskForm'
import Controls from './components/Controls'
import Timeline from './components/Timeline'
import ErrorBanner from './components/ErrorBanner'
import RehydratedSessionView from './components/RehydratedSessionView'
import { useSession } from './session/useSession'

/**
 * Agent Inspector -- minimal M1 client, re-plumbed onto the #20
 * foundation (Tailwind/shadcn + TanStack Query + the `need`/`busy`
 * reducer).
 *
 * Functionally unchanged from the pre-#20 prototype: create a
 * session, alternate get_next_step()/run_step(), and approve the
 * final TaskResult. The config rail and redesigned timeline are
 * #21/#22's scope, built on top of this; #24 (this change) adds
 * reload rehydration -- restoring a session from `?session=<id>` on
 * mount via `RehydratedSessionView` below.
 */
function App() {
  const {
    state,
    rehydrating,
    start,
    getNextStep,
    runNextStep,
    approve,
    reset,
  } = useSession()

  const hasSession = state.sessionId !== null
  const isDone = state.completedResult !== null

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-5 px-5 py-8 pb-16">
      <header>
        <h1 className="mb-1.5 text-2xl font-medium">Agent Inspector</h1>
        <p className="text-sm text-muted-foreground">
          Step through <code className="font-mono">SupervisedTaskHandler</code>{' '}
          one call at a time.
        </p>
      </header>

      {state.error && <ErrorBanner error={state.error} />}

      {!hasSession ? (
        rehydrating ? (
          <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
            Restoring session…
          </p>
        ) : (
          <TaskForm onCreate={start} disabled={state.busy} />
        )
      ) : (
        <section className="flex flex-col gap-4.5">
          <div className="flex flex-col gap-2 rounded-lg border px-4.5 py-3.5">
            <div>
              <span className="text-[10.5px] font-semibold tracking-wide text-muted-foreground uppercase">
                session
              </span>
              <div>
                <code className="font-mono text-sm">{state.sessionId}</code>
              </div>
            </div>
            <div>
              <span className="text-[10.5px] font-semibold tracking-wide text-muted-foreground uppercase">
                task
              </span>
              <p className="text-sm">
                {state.task?.instruction ??
                  (state.rehydrated
                    ? '(not returned by GET /api/sessions/{id} — see rollout below)'
                    : '')}
              </p>
            </div>
            <div>
              <span className="text-[10.5px] font-semibold tracking-wide text-muted-foreground uppercase">
                tools
              </span>
              <div>
                <code className="font-mono text-sm">
                  {state.tools.join(', ') || '(none)'}
                </code>
              </div>
            </div>
            {isDone && (
              <Button
                type="button"
                variant="outline"
                onClick={reset}
                className="self-start"
              >
                Start new session
              </Button>
            )}
          </div>

          <Controls
            need={state.need}
            busy={state.busy}
            onGetNextStep={getNextStep}
            onRunStep={runNextStep}
          />

          {state.rehydrated && (
            <RehydratedSessionView
              rollout={state.rollout ?? ''}
              toolCallHistory={state.toolCallHistory}
              stepCounter={state.stepCounter}
              config={state.config}
              need={state.need}
            />
          )}

          <Timeline
            entries={state.timeline}
            pendingResult={state.pendingResult}
            completedResult={state.completedResult}
            need={state.need}
            busy={state.busy}
            onApprove={approve}
          />
        </section>
      )}
    </div>
  )
}

export default App
