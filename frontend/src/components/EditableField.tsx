import { type ReactNode, useEffect, useRef, useState } from 'react'
import { Pencil } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

interface EditableFieldProps {
  /** The canonical, server-authoritative value -- seeds the draft
   * textarea, and is diffed against its own original value to derive
   * the `edited` badge. */
  value: string
  /** What to show in read mode. Defaults to a plain `<p>` of `value`,
   * but callers (e.g. `WorkerCard`'s streaming-cursor reveal) can pass
   * something richer without affecting the edit/diff plumbing. */
  displayValue?: ReactNode
  label: string
  /** Whether this field is *currently* the single most-recent eligible
   * entry per #22 (gated by the caller on `need`/`busy`). */
  editable: boolean
  /** `SessionState.busy` -- disables the toggle/textarea mid-request. */
  busy: boolean
  onSave: (value: string) => void
}

/**
 * Inline `Textarea` editing for a `TaskStep.instruction` /
 * `TaskStepResult.content` field, toggled by a single Edit/Done
 * button. Tracks its own `edited` flag by diffing the live `value`
 * prop against the value it first saw -- `TimelineEntry` itself has no
 * `edited` field (the reducer just replaces `step`/`result` in place),
 * so this is the client-side substitute the issue calls for.
 */
function EditableField({
  value,
  displayValue,
  label,
  editable,
  busy,
  onSave,
}: EditableFieldProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const [edited, setEdited] = useState(false)
  const originalValueRef = useRef(value)

  useEffect(() => {
    if (value !== originalValueRef.current) setEdited(true)
  }, [value])

  // If this field stops being the editable one mid-edit (e.g. a new
  // operation started elsewhere while the textarea was left open),
  // fall back to read mode -- derived at render time, rather than an
  // effect that would fire a second, cascading render just to unwind
  // `isEditing`.
  const showEditor = isEditing && editable

  function handleToggle() {
    if (isEditing) {
      const trimmed = draft.trim()
      if (trimmed && trimmed !== value) onSave(trimmed)
      setIsEditing(false)
      return
    }
    setDraft(value)
    setIsEditing(true)
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-1.5">
        <span className="text-[10.5px] font-semibold tracking-wide text-muted-foreground uppercase">
          {label}
        </span>
        {edited && (
          <Badge
            variant="outline"
            className="h-4.5 px-1.5 text-[10px] font-normal"
          >
            edited
          </Badge>
        )}
        {editable && (
          <Button
            type="button"
            variant="ghost"
            size="xs"
            disabled={busy}
            onClick={handleToggle}
            className="ml-auto text-[10.5px]"
          >
            <Pencil />
            {isEditing ? 'Done' : 'Edit'}
          </Button>
        )}
      </div>
      {showEditor ? (
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={busy}
          autoFocus
          className="font-mono text-sm"
        />
      ) : (
        (displayValue ?? <p className="text-sm">{value}</p>)
      )}
    </div>
  )
}

export default EditableField
