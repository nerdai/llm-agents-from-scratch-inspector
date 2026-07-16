import { type ReactNode, useState } from 'react'
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
   * but callers (e.g. `StepResultCard`'s streaming-cursor reveal) can pass
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
  // A one-time-initialized value read during render, not a ref (this
  // lint config's `react-hooks/refs` rule disallows reading
  // `ref.current` during render -- refs are an effects/event-handler
  // escape hatch, not a rendering input).
  const [originalValue] = useState(value)

  // Derived, not one-way-latched state: a save that reverts `value`
  // back to what it started as un-marks `edited` again, rather than
  // sticking once true.
  const edited = value !== originalValue

  // If this field stops being the editable one (e.g. a new operation
  // started elsewhere while the textarea was left open), fall back to
  // read mode -- and make that sticky, not just the rendered output,
  // so a later `editable: true` on a *different* operation can't
  // silently reopen this field's editor. React's documented pattern
  // for resetting state in response to a prop change during render
  // (not an effect, which would cause an extra cascading render):
  // https://react.dev/learn/you-might-not-need-an-effect#adjusting-some-state-when-a-prop-changes
  const [prevEditable, setPrevEditable] = useState(editable)
  if (editable !== prevEditable) {
    setPrevEditable(editable)
    if (!editable) setIsEditing(false)
  }

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
