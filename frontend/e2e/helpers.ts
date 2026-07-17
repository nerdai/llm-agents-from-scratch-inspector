import { expect, type Page } from '@playwright/test'

/**
 * Shared helpers for the Playwright E2E suite (issue #62).
 *
 * Every test in this suite drives the same scripted backend (see
 * `fixtures/scripted_agent.py`), whose LLM understands exactly one
 * convention: a task instruction (or an edited step instruction)
 * embeds a literal `x=<N>` for the next `next_number(x)` call, and
 * every step result it produces back is a bare integer string. This
 * file's `hailstoneTask()` is the one place that convention is
 * encoded on the test side, so every spec constructs its task text
 * through it rather than hand-writing `x=<N>` strings inline.
 */

/** A task instruction the scripted LLM (`fixtures/scripted_agent.py`)
 * understands: it embeds `x=<N>`, the literal token the fixture's
 * regex-based LLM reads back out to drive `next_number(x)`. */
export function hailstoneTask(x: number): string {
  return `Compute next_number starting from x=${x} until you reach 1.`
}

/**
 * Fills the task form and submits "Create session", waiting for the
 * new session to actually exist (not just for the click to fire) --
 * proven by the `?session=<id>` query param `useSession`'s URL-sync
 * effect writes once `state.sessionId` is set (see `useSession.ts`).
 *
 * Returns the new session id, read from the URL rather than scraped
 * out of the config rail's DOM -- the same mechanism the reload-
 * rehydration flow itself depends on, so using it here doubles as an
 * implicit check that session-id round-tripping through the URL
 * actually works.
 */
export async function createSession(page: Page, task: string): Promise<string> {
  await page.goto('/')
  await page.locator('#task-input').fill(task)
  await page.getByRole('button', { name: 'Create session' }).click()
  await expect
    .poll(() => new URL(page.url()).searchParams.get('session'))
    .not.toBeNull()
  return new URL(page.url()).searchParams.get('session')!
}

/** Clicks `get_next_step()` and waits for the phase badge to leave
 * "Calling backend…", i.e. for the mutation to actually resolve. */
export async function clickGetNextStep(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'get_next_step()' }).click()
  await expect(phaseBadge(page)).not.toHaveText('Calling backend…')
}

/** Clicks `run_step(step)` and waits for it to resolve (see
 * `clickGetNextStep`). */
export async function clickRunStep(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'run_step(step)' }).click()
  await expect(phaseBadge(page)).not.toHaveText('Calling backend…')
}

/** The phase-status `Badge` in the top app bar (`Controls.tsx`) --
 * "Awaiting get_next_step()" / "Awaiting run_step(step)" / "Awaiting
 * approval — complete the task" / "Task complete" / "Aborted" (or
 * "Calling backend…" mid-mutation). No test id on the element itself
 * -- its own text is already the unique, meaningful thing to assert
 * on, so this just scopes to the one `<header>` `Controls` renders
 * into, ruling out any other element that might coincidentally share
 * wording elsewhere on the page. */
export function phaseBadge(page: Page) {
  return page
    .locator('header')
    .getByText(/^(Awaiting|Task complete|Aborted|Calling backend)/)
}
