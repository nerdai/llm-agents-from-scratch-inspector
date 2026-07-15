import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { highlightText } from '@/lib/highlight'

interface HighlightedBlockProps {
  code: string
  className?: string
}

/**
 * Shiki-highlighted text block shared by the templates and rollout
 * drawers (#23). Renders a plain `<pre>` immediately (so content shows
 * up even before Shiki's async grammar/theme load resolves), then
 * swaps in the highlighted HTML once it's ready.
 */
function HighlightedBlock({ code, className }: HighlightedBlockProps) {
  // Keyed by `code` (rather than reset-then-set) so the effect never
  // calls `setState` synchronously within its body -- only from the
  // async `.then`, once the highlighted result for *this* `code` is
  // ready.
  const [result, setResult] = useState<{ code: string; html: string } | null>(
    null,
  )

  useEffect(() => {
    let cancelled = false
    void highlightText(code).then((html) => {
      if (!cancelled) setResult({ code, html })
    })
    return () => {
      cancelled = true
    }
  }, [code])

  const html = result?.code === code ? result.html : null

  if (html === null) {
    return (
      <pre
        className={cn(
          'overflow-x-auto rounded-lg border bg-muted/30 p-3 text-xs whitespace-pre-wrap',
          className,
        )}
      >
        {code}
      </pre>
    )
  }

  return (
    <div
      className={cn(
        'overflow-x-auto rounded-lg border text-xs [&_pre]:!p-3 [&_pre]:whitespace-pre-wrap [&_pre]:break-words',
        className,
      )}
      // Shiki's own output -- not user-controlled input (templates and
      // rollout text both come from the trusted local backend process
      // this dev tool is driving).
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

export default HighlightedBlock
