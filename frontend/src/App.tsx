import AppShell from './components/AppShell'
import ConfigRail from './components/ConfigRail'
import Controls from './components/Controls'
import Timeline from './components/Timeline'
import ErrorBanner from './components/ErrorBanner'
import { useSession } from './session/useSession'

/**
 * Agent Inspector -- full-viewport app-bar layout (#21): a persistent
 * config rail (task input, Ollama status, skills scope/explicit-only,
 * discovered tools/skills) alongside a main content area that drives
 * one `SupervisedTaskHandler` call at a time.
 *
 * `AppShell` owns only the chrome (app bar + rail + scrollable main
 * slot); `ConfigRail` owns the rail's contents. The `<main>` slot
 * below still renders this project's pre-#21 `Controls`/`Timeline` --
 * #22 (timeline/operation-card redesign), #23 (drawers, approval
 * gate, error toasts), and #24 (reload rehydration) build on top of
 * that slot's contents, not this file's top-level structure.
 */
function App() {
  const { state, start, getNextStep, runNextStep, approve, reset } =
    useSession()

  return (
    <AppShell
      rail={<ConfigRail state={state} onCreate={start} onReset={reset} />}
    >
      {state.error && <ErrorBanner error={state.error} />}

      {state.sessionId !== null && (
        <>
          <Controls
            need={state.need}
            busy={state.busy}
            onGetNextStep={getNextStep}
            onRunStep={runNextStep}
          />

          <Timeline
            entries={state.timeline}
            pendingResult={state.pendingResult}
            completedResult={state.completedResult}
            need={state.need}
            busy={state.busy}
            onApprove={approve}
          />
        </>
      )}
    </AppShell>
  )
}

export default App
