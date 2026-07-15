import AppShell from './components/AppShell'
import ConfigRail from './components/ConfigRail'
import Controls from './components/Controls'
import Timeline from './components/Timeline'
import ErrorBanner from './components/ErrorBanner'
import RehydratedSessionView from './components/RehydratedSessionView'
import { useSession } from './session/useSession'

/**
 * Agent Inspector -- full-viewport app-bar layout (#21): a persistent
 * config rail (task input, Ollama status, skills scope/explicit-only,
 * discovered tools/skills) alongside a main content area that drives
 * one `SupervisedTaskHandler` call at a time.
 *
 * `AppShell` owns only the chrome (app bar + rail + scrollable main
 * slot); `ConfigRail` owns the rail's contents, including `TaskForm`
 * pre-session. The `<main>` slot below renders `Controls`/`Timeline`
 * (#22's redesign) once a session exists, reload rehydration via
 * `RehydratedSessionView` (#24) when one was restored from
 * `?session=<id>`, and #23's drawers/approval gate/error toasts build
 * on top of this too.
 */
function App() {
  const {
    state,
    rehydrating,
    start,
    getNextStep,
    runNextStep,
    approve,
    editStep,
    editResult,
    reset,
  } = useSession()

  const hasSession = state.sessionId !== null

  return (
    <AppShell
      rail={<ConfigRail state={state} onCreate={start} onReset={reset} />}
    >
      {state.error && <ErrorBanner error={state.error} />}

      {!hasSession && rehydrating && (
        <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          Restoring session…
        </p>
      )}

      {hasSession && (
        <>
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
            onEditStep={editStep}
            onEditResult={editResult}
          />
        </>
      )}
    </AppShell>
  )
}

export default App
