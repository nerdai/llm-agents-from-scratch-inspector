import { useQuery } from '@tanstack/react-query'
import { fetchTemplates } from '../client'
import { queryKeys } from '../queryKeys'

/**
 * `GET /api/templates` -- the framework's default prompt templates.
 * Not session-scoped: every session's agent shares the same module-
 * level defaults (see `routes/session.py`'s `get_default_templates`).
 */
export function useTemplates() {
  return useQuery({
    queryKey: queryKeys.templates,
    queryFn: fetchTemplates,
  })
}
