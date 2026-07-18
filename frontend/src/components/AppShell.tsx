import type { ReactNode } from 'react'
import ModeToggle from './ModeToggle'
import OllamaStatusChip from './OllamaStatusChip'

interface AppShellProps {
  /** The config rail's contents (#21 -- `ConfigRail`). Rendered inside
   * a fixed-width, independently-scrollable `<aside>`. */
  rail: ReactNode
  /** Optional extra app-bar content, rendered before the Ollama status
   * chip -- e.g. `Controls` (phase badge, abort), which is global to
   * the current session rather than scoped to the scrollable timeline
   * beneath it, so it belongs in the one persistent bar rather than a
   * second pinned header inside `<main>`. */
  headerEnd?: ReactNode
  /** Optional content pinned to the right edge of the main content
   * area, spanning its full height alongside `children` -- e.g.
   * `RolloutPanel`, a persistent collapsible panel rather than an
   * overlay, so it can stay open beside the timeline instead of
   * covering it. Independently scrollable, same as `rail`. */
  sidePanel?: ReactNode
  /** The main content area -- today this is `App.tsx`'s
   * `Timeline` (plus `RehydratedSessionView` when applicable), but
   * #22/#24 own what actually renders here; this component only owns
   * the surrounding chrome (app bar + rail + sticky header + scroll
   * container), not the content. */
  children: ReactNode
}

/**
 * Full-viewport app-bar layout (#21): a persistent top app bar, a
 * fixed-width config rail on the left, and a scrollable main content
 * area on the right -- replacing the previous centered single-column
 * layout.
 *
 * Deliberately a thin, content-agnostic wrapper: it accepts `rail`,
 * `headerEnd`, `sidePanel`, and `children` as slots rather than
 * hard-coding what goes in them. `sidePanel` sits beside `children` in
 * a shared row, each independently scrollable, so a panel like
 * `RolloutPanel` can stay open without covering or shrinking the
 * timeline's own scroll position.
 */
function AppShell({ rail, headerEnd, sidePanel, children }: AppShellProps) {
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      <header className="grid h-14 flex-none grid-cols-[1fr_auto_1fr] items-center gap-3.5 border-b bg-card px-5">
        <div className="flex items-center justify-self-start gap-2">
          <img src="/logo.svg" alt="" className="size-6.5" />
          <span className="text-[15px] font-bold tracking-tight">
            Agent Inspector
          </span>
        </div>
        <span className="justify-self-center font-mono text-[11px] font-semibold text-muted-foreground">
          SupervisedTaskHandler
        </span>
        <div className="flex items-center justify-self-end gap-3.5">
          {headerEnd}
          <OllamaStatusChip />
          <ModeToggle />
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="w-80 flex-none overflow-y-auto border-r bg-muted/30">
          {rail}
        </aside>
        <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <div className="flex min-h-0 flex-1">
            <div className="min-h-0 min-w-0 flex-1 overflow-y-auto">
              <div className="flex flex-col gap-4.5 px-9 py-8 pb-16">
                {children}
              </div>
            </div>
            {sidePanel}
          </div>
        </main>
      </div>
    </div>
  )
}

export default AppShell
