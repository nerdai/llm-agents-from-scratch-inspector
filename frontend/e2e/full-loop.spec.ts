import { expect, test } from '@playwright/test'
import {
  clickGetNextStep,
  clickRunStep,
  createSession,
  hailstoneTask,
  phaseBadge,
} from './helpers'

/**
 * The full supervised loop, start to finish, against the real backend
 * (see `fixtures/scripted_agent.py`): create -> get_next_step() ->
 * run_step() -> edit the pending step -> run it -> edit its result ->
 * get_next_step() again (now routed straight to a final result by the
 * edited "1") -> approve.
 *
 * One long, linear test rather than several smaller ones -- each
 * stage's assertions depend on UI state produced by the previous
 * stage, so splitting it up would mean either re-deriving that state
 * per test (duplicated, and could silently drift from the real
 * sequence) or chaining fixtures in a way that's harder to follow than
 * the loop's own chronology. Mirrors
 * `tests/test_integration_loop.py::TestHailstoneFromFourEndToEnd`'s
 * own reasoning for doing the same thing at the HTTP-route level.
 */
test('create, next-step, run-step, edit step + result, approve', async ({
  page,
}) => {
  const task = hailstoneTask(4)
  await createSession(page, task)
  await expect(phaseBadge(page)).toHaveText('Awaiting get_next_step()')

  // 1. get_next_step(): the deterministic first call, no LLM
  // consulted -- the proposed step is the task instruction verbatim.
  await clickGetNextStep(page)
  await expect(phaseBadge(page)).toHaveText('Awaiting run_step(step)')
  await expect(page.getByText('decided')).toBeVisible()
  // Both the "reasoning" block and the editable step field show the
  // same text at this point (decision.content === step.instruction
  // for the deterministic first call) -- `.first()` avoids a
  // strict-mode violation on the duplicate match.
  await expect(page.getByText(task).first()).toBeVisible()

  // 2. Edit the pending step before running it -- the edited
  // instruction ("x=6") is what run_step() actually executes, not the
  // original ("x=4"), proving the edit really reaches the backend.
  await page.getByRole('button', { name: 'Edit' }).click()
  await page.locator('textarea').fill('Call next_number with x=6.')
  await page.getByRole('button', { name: 'Done' }).click()
  await expect(page.getByText('edited').first()).toBeVisible()
  await expect(page.getByText('Call next_number with x=6.')).toBeVisible()

  // 3. run_step(step): executes the real next_number(6) tool call
  // (6 is even -> 3), not scripted -- proving the edited instruction
  // drove a real tool execution.
  await clickRunStep(page)
  await expect(phaseBadge(page)).toHaveText('Awaiting get_next_step()')
  await expect(page.getByText('next_number({"x":6})')).toBeVisible()

  // 4. Edit the step's result before the next get_next_step() call --
  // forcing it to "1" (the Hailstone sequence's fixed point) short-
  // circuits what would otherwise take several more real steps to
  // reach, and proves the edited *result* (not just the edited step)
  // is what the next routing decision actually sees.
  await page.getByRole('button', { name: 'Edit' }).click()
  await page.locator('textarea').fill('1')
  await page.getByRole('button', { name: 'Done' }).click()
  await expect(page.getByText('edited').first()).toBeVisible()

  // 5. get_next_step(): the scripted LLM reads the edited "1" back out
  // of <current-response> and routes straight to a final result.
  await clickGetNextStep(page)
  await expect(phaseBadge(page)).toHaveText(
    'Awaiting approval — complete the task',
  )
  await expect(page.getByRole('button', { name: 'Approve' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reject' })).toBeVisible()

  // 6. Approve, behind its confirm dialog.
  await page.getByRole('button', { name: 'Approve' }).click()
  const dialog = page.getByRole('alertdialog')
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Approve' }).click()

  await expect(phaseBadge(page)).toHaveText('Task complete')
  await expect(page.getByText('resolved')).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Start new session' }),
  ).toBeVisible()
})
