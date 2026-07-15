import type { ReactNode } from 'react'
import OllamaStatusChip from './OllamaStatusChip'

interface AppShellProps {
  /** The config rail's contents (#21 -- `ConfigRail`). Rendered inside
   * a fixed-width, independently-scrollable `<aside>`. */
  rail: ReactNode
  /** The main content area -- today this is `App.tsx`'s
   * error banner + `Controls` + `Timeline`, but #22-#24 own what
   * actually renders here; this component only owns the surrounding
   * chrome (app bar + rail + scroll container), not the content. */
  children: ReactNode
}

/**
 * Full-viewport app-bar layout (#21): a persistent top app bar, a
 * fixed-width config rail on the left, and a scrollable main content
 * area on the right -- replacing the previous centered single-column
 * layout.
 *
 * Deliberately a thin, content-agnostic wrapper: it accepts `rail` and
 * `children` as slots rather than hard-coding what goes in them, so
 * #22 (timeline/operation cards), #23 (drawers, approval gate, error
 * toasts), and #24 (reload rehydration) can build inside the `<main>`
 * slot without needing to also restructure this shell.
 */
function AppShell({ rail, children }: AppShellProps) {
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
        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto flex max-w-3xl flex-col gap-4.5 px-5 py-8 pb-16">
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}

export default AppShell
