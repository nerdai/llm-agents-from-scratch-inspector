import './App.css'
import TaskForm from './components/TaskForm'
import Controls from './components/Controls'
import Timeline from './components/Timeline'
import ErrorBanner from './components/ErrorBanner'
import { useSession } from './session/useSession'

/**
 * Agent Inspector -- minimal M1 client.
 *
 * Lets a human manually drive `LLMAgent.SupervisedTaskHandler` one call
 * at a time: create a session, alternate get_next_step()/run_step(),
 * and approve the final TaskResult. This is a bare-bones exercise of
 * the loop; the full shadcn/Tailwind/TanStack Query UI lands in M4.
 */
function App() {
  const { state, start, getNextStep, runNextStep, approve, reset } =
    useSession()

  const hasSession = state.sessionId !== null
  const isDone = state.completedResult !== null

  return (
    <div id="inspector">
      <header className="app-header">
        <h1>Agent Inspector</h1>
        <p className="subtitle">
          Step through <code>SupervisedTaskHandler</code> one call at a time.
        </p>
      </header>

      {state.error && <ErrorBanner message={state.error} />}

      {!hasSession ? (
        <TaskForm onCreate={start} disabled={state.loading} />
      ) : (
        <section className="session-panel">
          <div className="session-meta">
            <div>
              <span className="kv-label">session</span>
              <code>{state.sessionId}</code>
            </div>
            <div>
              <span className="kv-label">task</span>
              <p className="kv-value">{state.task?.instruction}</p>
            </div>
            <div>
              <span className="kv-label">tools</span>
              <code>{state.tools.join(', ') || '(none)'}</code>
            </div>
            {isDone && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={reset}
              >
                Start new session
              </button>
            )}
          </div>

          <Controls
            need={state.need}
            loading={state.loading}
            onGetNextStep={getNextStep}
            onRunStep={runNextStep}
          />

          <Timeline
            entries={state.timeline}
            finalResult={state.finalResult}
            completedResult={state.completedResult}
            need={state.need}
            loading={state.loading}
            onApprove={approve}
          />
        </section>
      )}
    </div>
  )
}

export default App
