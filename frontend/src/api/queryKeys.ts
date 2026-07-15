/**
 * Centralized TanStack Query key factory.
 *
 * One place for cache keys keeps `hooks/*.ts` (queries) and any
 * future invalidation call sites (mutations that need to refresh a
 * sibling query) from drifting apart on ad-hoc key arrays.
 */
export const queryKeys = {
  health: ['health'] as const,
  ollamaStatus: ['ollama', 'status'] as const,
  templates: ['templates'] as const,
  session: (sessionId: string) => ['session', sessionId] as const,
  sessionRollout: (sessionId: string) =>
    ['session', sessionId, 'rollout'] as const,
}
