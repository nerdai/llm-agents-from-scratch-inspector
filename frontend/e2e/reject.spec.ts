import { expect, test } from '@playwright/test'
import {
  clickGetNextStep,
  clickRunStep,
  createSession,
  hailstoneTask,
  phaseBadge,
} from './helpers'

/**
 * The reject path (TRD §6.5, issue #11): rejecting a proposed
 * `TaskResult` discards it and routes back to `need === "next"`
 * without consulting the LLM (the framework's own
 * `RejectedTaskResult` short-circuit -- see
 * `LLMAgent.TaskHandler.get_next_step`), with the operator's feedback
 * recorded server-side rather than shown as a new timeline card (#23
 * owns any dedicated feedback surfacing; not in scope here).
 *
 * `x=2` reaches the Hailstone sequence's fixed point (`1`) after a
 * single real `run_step()` call (2 is even -> 1), the fastest path to
 * `need === "approve"` this suite's scripted LLM supports -- see
 * `fixtures/scripted_agent.py`.
 */
test('reject routes back to next without approving', async ({ page }) => {
  await createSession(page, hailstoneTask(2))
  await clickGetNextStep(page)
  await clickRunStep(page)
  await clickGetNextStep(page)

  await expect(phaseBadge(page)).toHaveText(
    'Awaiting approval — complete the task',
  )
  await expect(page.getByRole('button', { name: 'Reject' })).toBeVisible()

  await page.getByRole('button', { name: 'Reject' }).click()
  const dialog = page.getByRole('alertdialog')
  await expect(dialog).toBeVisible()
  await dialog
    .getByLabel('Feedback')
    .fill('Double-check the arithmetic and try again.')
  await dialog.getByRole('button', { name: 'Reject' }).click()

  // Back to `need === "next"`: the proposed result is gone, and
  // get_next_step() is the actionable call again -- not approved, not
  // aborted.
  await expect(phaseBadge(page)).toHaveText('Awaiting get_next_step()')
  await expect(page.getByRole('button', { name: 'Approve' })).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: 'get_next_step()' }),
  ).toBeEnabled()
})
