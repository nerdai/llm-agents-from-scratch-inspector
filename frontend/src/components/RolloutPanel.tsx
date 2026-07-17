import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useRollout } from '../api/hooks'
import HighlightedBlock from './HighlightedBlock'

interface RolloutPanelProps {
  sessionId: string | null
}

/**
 * The session's full rollout text, as a persistent right-side panel
 * spanning the main content area's full height rather than an overlay
 * drawer (the earlier `RolloutDrawer`) -- so it can stay open
 * alongside `Timeline` instead of covering it. Collapses to a narrow
 * vertical tab when not needed, handing that width back to the
 * timeline column.
 *
 * A plain toggle rather than the shared `ui/collapsible.tsx` primitive:
 * that component's transition is height-based (it measures and
 * animates `--collapsible-panel-height`), and this panel's content has
 * a fixed width instead -- reusing it would mean fighting its
 * transition-end detection, which is wired to the dimension *it*
 * manages, not an arbitrary one a consumer overrides.
 */
function RolloutPanel({ sessionId }: RolloutPanelProps) {
  const [open, setOpen] = useState(false)
  const { data, isLoading, isError, error, refetch } = useRollout(sessionId)

  const toggle = () => {
    const nextOpen = !open
    setOpen(nextOpen)
    if (nextOpen) void refetch()
  }

  return (
    <div className="flex flex-none border-l">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls="rollout-panel-content"
        className="flex w-9 flex-none flex-col items-center justify-between gap-2 bg-muted/20 py-3 hover:bg-muted/50"
      >
        <ChevronRight
          className={cn(
            'size-3.5 text-muted-foreground transition-transform',
            open && 'rotate-180',
          )}
        />
        <span className="rotate-180 font-mono text-[10px] font-semibold tracking-wide text-muted-foreground uppercase [writing-mode:vertical-rl]">
          Rollout
        </span>
        <span aria-hidden className="size-3.5" />
      </button>
      <div
        id="rollout-panel-content"
        className={`overflow-hidden transition-[width] duration-200 ease-out ${open ? 'w-96' : 'w-0'}`}
      >
        <div className="flex h-full w-96 flex-col gap-3 overflow-y-auto p-4">
          <div>
            <h2 className="text-sm font-semibold">Session rollout</h2>
            <p className="text-xs text-muted-foreground">
              The full rollout text driving this session&apos;s agent.
            </p>
          </div>
          {isLoading && (
            <p className="text-sm text-muted-foreground">Loading rollout…</p>
          )}
          {isError && (
            <p className="text-sm text-destructive">
              Failed to load rollout
              {error instanceof Error ? `: ${error.message}` : '.'}
            </p>
          )}
          {data && <HighlightedBlock code={data.rollout} />}
        </div>
      </div>
    </div>
  )
}

export default RolloutPanel
