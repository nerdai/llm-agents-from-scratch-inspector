import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { Need } from '../api/types'

interface StepActionButtonsProps {
  need: Need | null
  busy: boolean
  onGetNextStep: () => void
  onRunStep: () => void
}

/**
 * The get_next_step()/run_step() action pair, rendered inline next to
 * whichever step is current (`Timeline` owns exactly where) rather
 * than pinned in a fixed toolbar -- the action you'd take next lives
 * right beside the content it acts on, not off in a separate bar you
 * have to look away to find.
 *
 * Whichever call is currently actionable gets a strong, role-colored
 * "do this now" treatment (violet for get_next_step(), near-black for
 * run_step()) plus a pulsing ring, mirroring the prototype's own
 * alternating-highlight buttons -- get_next_step() and run_step() are
 * one alternating pair the *same* LLM agent drives for every call (the
 * human operator is the actual overseer in this "supervised" loop, not
 * either button), never both "live" at once, so exactly one should
 * visually read as the next action.
 */
function StepActionButtons({
  need,
  busy,
  onGetNextStep,
  onRunStep,
}: StepActionButtonsProps) {
  const canNext = need === 'next' && !busy
  const canRun = need === 'run' && !busy

  const nextButtonClassName = cn(
    'w-full font-mono',
    canNext
      ? 'animate-pulse-ring bg-primary text-primary-foreground hover:bg-primary/90 [--pulse-color:var(--primary)]'
      : 'bg-muted text-muted-foreground hover:bg-muted',
  )
  const runButtonClassName = cn(
    'w-full font-mono',
    canRun
      ? 'animate-pulse-ring bg-foreground text-background hover:bg-foreground/90 [--pulse-color:var(--foreground)]'
      : 'bg-muted text-muted-foreground hover:bg-muted',
  )

  return (
    <div className="flex flex-col gap-2">
      <Button
        type="button"
        variant="ghost"
        disabled={!canNext}
        onClick={onGetNextStep}
        className={nextButtonClassName}
      >
        get_next_step()
      </Button>
      <Button
        type="button"
        variant="ghost"
        disabled={!canRun}
        onClick={onRunStep}
        className={runButtonClassName}
      >
        run_step(step)
      </Button>
    </div>
  )
}

export default StepActionButtons
