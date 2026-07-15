import { useEffect } from 'react'
import { toast } from 'sonner'
import { Toaster } from '@/components/ui/sonner'
import AppShell from './components/AppShell'
import ConfigRail from './components/ConfigRail'
import Controls from './components/Controls'
import Timeline from './components/Timeline'
import TemplatesDrawer from './components/TemplatesDrawer'
import { useSession } from './session/useSession'

/**
 * Agent Inspector -- full-viewport app-bar layout (#21): a persistent
 * config rail (task input, Ollama status, skills scope/explicit-only,
 * discovered tools/skills) alongside a main content area that drives
 * one `SupervisedTaskHandler` call at a time.
 *
 * `AppShell` owns only the chrome (app bar + rail + scrollable main
 * slot); `ConfigRail` owns the rail's contents. The `<main>` slot
 * below renders `Controls`/`Timeline` (#22's redesign, including the
 * approve/reject gate and inline editing) and #23's `TemplatesDrawer`
 * trigger lives in the app bar itself (`AppShell`'s `headerActions`
 * slot) since it needs to be usable before any session exists.
 */
function App() {
  const {
    state,
    start,
    getNextStep,
    runNextStep,
    approve,
    reject,
    editStep,
    editResult,
    reset,
  } = useSession()

  // Surfaces every failed mutation as a toast (#23) -- `state.error` is
  // a fresh object each time `busy/error` fires (see `useSession`'s
  // `toErrorInfo`), and is reset to `null` at the start of the next
  // mutation, so this fires exactly once per failure.
  useEffect(() => {
    if (!state.error) return
    toast.error(
      `Request failed${state.error.status ? ` (HTTP ${state.error.status})` : ''}`,
      { description: state.error.detail },
    )
  }, [state.error])

  return (
    <AppShell
      rail={<ConfigRail state={state} onCreate={start} onReset={reset} />}
      headerActions={<TemplatesDrawer />}
    >
      <Toaster />

      {state.sessionId !== null && (
        <>
          <Controls
            need={state.need}
            busy={state.busy}
            sessionId={state.sessionId}
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
            onReject={reject}
            onEditStep={editStep}
            onEditResult={editResult}
          />
        </>
      )}
    </AppShell>
  )
}

export default App
