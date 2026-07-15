import { useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { useRollout } from '../api/hooks'
import HighlightedBlock from './HighlightedBlock'

interface RolloutDrawerProps {
  sessionId: string | null
}

/**
 * `GET /api/sessions/{id}/rollout` -- only meaningful once a session
 * exists, so the trigger is disabled until then. Refetches on every
 * open (rather than relying on the cached query) so it reflects
 * whatever step the session has advanced to since it was last opened.
 */
function RolloutDrawer({ sessionId }: RolloutDrawerProps) {
  const [open, setOpen] = useState(false)
  const { data, isLoading, isError, error, refetch } = useRollout(sessionId)

  return (
    <Sheet
      open={open}
      onOpenChange={(nextOpen: boolean) => {
        setOpen(nextOpen)
        if (nextOpen) void refetch()
      }}
    >
      <SheetTrigger
        render={
          <Button type="button" variant="outline" disabled={!sessionId} />
        }
      >
        Rollout
      </SheetTrigger>
      <SheetContent side="right" className="w-full sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>Session rollout</SheetTitle>
          <SheetDescription>
            The full rollout text driving this session&apos;s agent.
          </SheetDescription>
        </SheetHeader>
        <div className="flex flex-col gap-3 overflow-y-auto px-4 pb-4">
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
      </SheetContent>
    </Sheet>
  )
}

export default RolloutDrawer
