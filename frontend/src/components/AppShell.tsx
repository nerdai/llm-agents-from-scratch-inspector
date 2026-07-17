import type { ReactNode } from 'react'
import OllamaStatusChip from './OllamaStatusChip'

interface AppShellProps {
  /** The config rail's contents (#21 -- `ConfigRail`). Rendered inside
   * a fixed-width, independently-scrollable `<aside>`. */
  rail: ReactNode
  /** Optional content pinned to the top of the main content area,
   * above the independently-scrollable `children` below it -- e.g.
   * `Controls` (get_next_step()/run_step()/abort), so it stays
   * reachable while a long `Timeline` scrolls underneath instead of
   * requiring a scroll back up to reach it. */
  mainHeader?: ReactNode
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
 * `mainHeader`, `sidePanel`, and `children` as slots rather than
 * hard-coding what goes in them. `mainHeader` sits outside the
 * `<main>` scroll container (its own `flex-none` row), so pinned
 * content like `Controls` stays reachable without scrolling back up
 * through a long `children` (e.g. `Timeline`). `sidePanel` sits beside
 * `children` in a shared row, each independently scrollable, so a
 * panel like `RolloutPanel` can stay open without covering or
 * shrinking the timeline's own scroll position.
 */
function AppShell({ rail, mainHeader, sidePanel, children }: AppShellProps) {
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      <header className="flex h-14 flex-none items-center gap-3.5 border-b bg-card px-5">
        <div className="flex items-center gap-2">
          <span className="flex size-6.5 items-center justify-center rounded-md bg-primary text-xs font-extrabold text-primary-foreground">
            A
          </span>
          <span className="text-[15px] font-bold tracking-tight">
            Agent Inspector
          </span>
        </div>
        <span className="font-mono text-[11px] font-semibold text-muted-foreground">
          SupervisedTaskHandler
        </span>
        <div className="flex-1" />
        <OllamaStatusChip />
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="w-80 flex-none overflow-y-auto border-r bg-muted/30">
          {rail}
        </aside>
        <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
          {mainHeader && (
            <div className="flex-none border-b bg-background px-9 py-3.5">
              {mainHeader}
            </div>
          )}
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
