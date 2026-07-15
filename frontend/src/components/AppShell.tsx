import type { ReactNode } from 'react'
import OllamaStatusChip from './OllamaStatusChip'

interface AppShellProps {
  /** The config rail's contents (#21 -- `ConfigRail`). Rendered inside
   * a fixed-width, independently-scrollable `<aside>`. */
  rail: ReactNode
  /** Optional extra app-bar controls, rendered before the Ollama
   * status chip -- e.g. #23's `TemplatesDrawer` trigger, which needs
   * to be visible/usable before any session exists (so it can't live
   * in the rail or `<main>`, both of which are session-scoped). */
  headerActions?: ReactNode
  /** Optional content pinned to the top of the main content area,
   * above the independently-scrollable `children` below it -- e.g.
   * `Controls` (get_next_step()/run_step()/abort), so it stays
   * reachable while a long `Timeline` scrolls underneath instead of
   * requiring a scroll back up to reach it. */
  mainHeader?: ReactNode
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
 * `mainHeader`, and `children` as slots rather than hard-coding what
 * goes in them. `mainHeader` sits outside the `<main>` scroll
 * container (its own `flex-none` row), so pinned content like
 * `Controls` stays reachable without scrolling back up through a long
 * `children` (e.g. `Timeline`).
 */
function AppShell({
  rail,
  headerActions,
  mainHeader,
  children,
}: AppShellProps) {
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
        {headerActions}
        <OllamaStatusChip />
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="w-80 flex-none overflow-y-auto border-r bg-muted/30">
          {rail}
        </aside>
        <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
          {mainHeader && (
            <div className="flex-none border-b bg-background px-5 py-3.5">
              <div className="mx-auto max-w-3xl">{mainHeader}</div>
            </div>
          )}
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto flex max-w-3xl flex-col gap-4.5 px-5 py-8 pb-16">
              {children}
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}

export default AppShell
