import { useEffect } from 'react'
import { toast } from 'sonner'
import { Toaster } from '@/components/ui/sonner'
import AppShell from './components/AppShell'
import ConfigRail from './components/ConfigRail'
import Controls from './components/Controls'
import Timeline from './components/Timeline'
import TemplatesDrawer from './components/TemplatesDrawer'
import RehydratedSessionView from './components/RehydratedSessionView'
import RolloutPanel from './components/RolloutPanel'
import { useSession } from './session/useSession'

/**
 * Agent Inspector -- full-viewport app-bar layout (#21): a persistent
 * config rail (task input, Ollama status, skills scope/explicit-only,
 * discovered tools/skills) alongside a main content area that drives
 * one `SupervisedTaskHandler` call at a time.
 *
 * `AppShell` owns only the chrome (app bar + rail + pinned main header
 * + side panel + scrollable main slot); `ConfigRail` owns the rail's
 * contents, including `TaskForm` pre-session. `Controls` (phase badge,
 * abort) is pinned via `AppShell`'s `mainHeader` slot, so it stays
 * reachable without scrolling back up through a long `Timeline`. The
 * get_next_step()/run_step() action pair isn't pinned, though --
 * `Timeline` renders it inline, beside whichever step is current, via
 * `StepActionButtons` (#22's redesign, including the approve/reject
 * gate and inline editing) -- which, along with reload rehydration via
 * `RehydratedSessionView` (#24) when one was restored from
 * `?session=<id>`, renders in the scrollable `children` slot.
 * `RolloutPanel` lives in `AppShell`'s `sidePanel` slot -- a persistent
 * collapsible panel beside the timeline rather than an overlay drawer,
 * so it can stay open without covering the cards it's next to. #23's
 * `TemplatesDrawer` trigger lives in the app bar itself (`AppShell`'s
 * `headerActions` slot) since it needs to be usable before any
 * session exists; its Sonner `<Toaster />` replaces the old inline
 * error banner.
 */
function App() {
  const {
    state,
    rehydrating,
    start,
    getNextStep,
    runNextStep,
    approve,
    reject,
    editStep,
    editResult,
    abort,
    reset,
  } = useSession()

  const hasSession = state.sessionId !== null

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
      mainHeader={
        hasSession && (
          <Controls
            need={state.need}
            busy={state.busy}
            isCompleted={state.completedResult !== null}
            onAbort={abort}
          />
        )
      }
      sidePanel={hasSession && <RolloutPanel sessionId={state.sessionId} />}
    >
      <Toaster />

      {!hasSession && rehydrating && (
        <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          Restoring session…
        </p>
      )}

      {hasSession && (
        <>
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
            onReject={reject}
            onEditStep={editStep}
            onEditResult={editResult}
            onGetNextStep={getNextStep}
            onRunStep={runNextStep}
          />
        </>
      )}
    </AppShell>
  )
}

export default App
