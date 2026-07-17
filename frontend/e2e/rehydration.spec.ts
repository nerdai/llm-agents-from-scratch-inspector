import { expect, test } from '@playwright/test'
import {
  clickGetNextStep,
  clickRunStep,
  createSession,
  hailstoneTask,
} from './helpers'

/**
 * Reload rehydration (issue #24, TRD §6.7): visiting `?session=<id>`
 * restores a session from `GET /api/sessions/{id}` and renders
 * `RehydratedSessionView` instead of the live, structured `Timeline`
 * cards -- see that component's own docstring for why (the backend's
 * `SessionStateResponse` only has a whole-conversation `rollout`
 * string and a flat `tool_call_history`, not the per-operation shape
 * a live session accumulates). Also covers the unknown-session-id
 * fallback: a `?session=` id the backend has never heard of (a 404)
 * must fail gracefully back to the ordinary "no session yet" form,
 * not get stuck or crash.
 */
test('reloading with ?session=<id> restores the session', async ({ page }) => {
  const task = hailstoneTask(4)
  const sessionId = await createSession(page, task)
  await clickGetNextStep(page)
  await clickRunStep(page)

  // A fresh navigation (not a client-side route change) -- exercises
  // the on-mount rehydration path in `useSession.ts`, which only ever
  // runs from a real page load's `?session=` query param.
  await page.goto(`/?session=${sessionId}`)

  await expect(page.getByText('rehydrated session')).toBeVisible()
  await expect(page.getByText('step 1', { exact: true })).toBeVisible()
  await expect(page.getByText('need = next')).toBeVisible()
  await expect(page.getByText('=== Task Step Start ===')).toBeVisible()
  await expect(page.getByText('tool call history (1)')).toBeVisible()
  await expect(page.getByText(/next_number/).first()).toBeVisible()

  // The config rail still reflects the restored session (not just the
  // rehydrated-view card) -- same session id round-tripped back out.
  await expect(page.locator('aside').getByText(sessionId)).toBeVisible()
})

test('an unknown ?session=<id> falls back to the create-session form', async ({
  page,
}) => {
  await page.goto('/?session=sess_does_not_exist_00000000')

  // Falls back to the ordinary pre-session form rather than hanging on
  // "Restoring session…" or crashing.
  await expect(page.locator('#task-input')).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Create session' }),
  ).toBeVisible()

  // The stale, now-known-bad `?session=` param is dropped from the URL
  // (`useSession.ts`'s URL-sync effect, once rehydration fails).
  await expect
    .poll(() => new URL(page.url()).searchParams.get('session'))
    .toBeNull()
})
