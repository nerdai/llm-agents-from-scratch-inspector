import { useState } from 'react'
import type { KeyboardEvent } from 'react'
import type { SkillScope } from '../api/types'

/**
 * State + handlers for the Skills Scope / Explicit-only Skills
 * configuration inputs -- lifted out of `TaskForm` (#88) so
 * `ConfigRail` can own one instance across the pre-session and
 * post-completion views alike. Blind inputs either way: the real
 * skill catalog isn't known until *after* a session exists
 * (`CreateSessionResponse.skills`), so this is a scope toggle + a
 * free-text tag list, not a pre-populated picker.
 */
export function useSkillsConfig() {
  const [scopes, setScopes] = useState<SkillScope[]>([])
  const [explicitSkills, setExplicitSkills] = useState<string[]>([])
  const [tagDraft, setTagDraft] = useState('')

  const toggleScope = (scope: SkillScope) => {
    setScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope],
    )
  }

  const commitTag = (draft: string) => {
    const name = draft.trim()
    if (!name) return
    setExplicitSkills((prev) => (prev.includes(name) ? prev : [...prev, name]))
    setTagDraft('')
  }

  const removeTag = (name: string) => {
    setExplicitSkills((prev) => prev.filter((s) => s !== name))
  }

  const handleTagKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      commitTag(tagDraft)
    } else if (e.key === 'Backspace' && tagDraft === '') {
      setExplicitSkills((prev) => prev.slice(0, -1))
    }
  }

  /** The pending tag draft folded into `explicitSkills` -- for a
   * submit handler that needs the final committed list without
   * waiting for a blur/Enter first (mirrors `commitTag`'s own dedup
   * rule). Also actually commits it into state (clearing `tagDraft`),
   * not just computing the value to submit -- `useSkillsConfig()` now
   * persists for `ConfigRail`'s whole lifetime (#88), so an
   * uncommitted draft used here but never folded into `explicitSkills`
   * would submit successfully yet never show up as a real tag
   * afterward (including in the post-completion view this same
   * instance feeds). Returns the computed list directly rather than
   * relying on `explicitSkills` after the `setExplicitSkills` above,
   * since state updates aren't visible synchronously in the same
   * call. */
  const commitPendingDraft = (): string[] => {
    const pending = tagDraft.trim()
    const next =
      pending && !explicitSkills.includes(pending)
        ? [...explicitSkills, pending]
        : explicitSkills
    if (pending) {
      setExplicitSkills(next)
      setTagDraft('')
    }
    return next
  }

  return {
    scopes,
    explicitSkills,
    tagDraft,
    setTagDraft,
    toggleScope,
    commitTag,
    removeTag,
    handleTagKeyDown,
    commitPendingDraft,
  }
}

export type SkillsConfig = ReturnType<typeof useSkillsConfig>
