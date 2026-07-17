import type { ReactNode } from 'react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type PillTone = 'neutral' | 'violet' | 'amber' | 'emerald'

const TONE_CLASSES: Record<PillTone, string> = {
  neutral: 'border-border text-muted-foreground',
  violet:
    'border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300',
  amber:
    'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  emerald:
    'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
}

interface StatusPillProps {
  tone?: PillTone
  /** Renders a small pulsing dot -- reserved for states that are
   * actually in flight (driven by `SessionState.busy`), not for
   * decorating already-completed cards. */
  pulse?: boolean
  className?: string
  children: ReactNode
}

/** A small, information-dense status indicator for the timeline's
 * domain cards (decision/result/pending-operation) -- deliberately
 * not just a bare shadcn `Badge`, per #22's "not shadcn" visual
 * language for this part of the UI. */
function StatusPill({
  tone = 'neutral',
  pulse = false,
  className,
  children,
}: StatusPillProps) {
  return (
    <Badge
      variant="outline"
      className={cn(
        'gap-1.5 font-mono text-[10px] font-semibold tracking-wide uppercase',
        TONE_CLASSES[tone],
        className,
      )}
    >
      {pulse && (
        <span className="size-1.5 shrink-0 animate-pulse rounded-full bg-current" />
      )}
      {children}
    </Badge>
  )
}

export default StatusPill
