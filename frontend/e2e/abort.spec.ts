import { expect, test } from '@playwright/test'
import { createSession, hailstoneTask, phaseBadge } from './helpers'

/**
 * The abort flow (TRD §6.6, issue #12): a destructive, confirm-dialog-
 * gated action in the top app bar (`Controls.tsx`) that ends a session
 * immediately, from any `need` state. The resulting `need === "done"`
 * must render as "Aborted" -- distinct from an approved "Task
 * complete" (`Controls`'s `isCompleted` prop, sourced from whether a
 * real `TaskResult` exists) -- and the config rail's "Start new
 * session" affordance (`ConfigRail`'s `isDone` check) must appear
 * either way, not just after approval.
 */
test('abort ends the session and shows "Aborted", not "Task complete"', async ({
  page,
}) => {
  await createSession(page, hailstoneTask(4))
  await expect(phaseBadge(page)).toHaveText('Awaiting get_next_step()')

  // Scoped to `<header>` throughout -- the confirm dialog (portalled
  // outside it) has its own, separately-labeled "Abort" action button,
  // and Base UI's alert-dialog popup can briefly remain in the DOM
  // after closing, which would otherwise make an unscoped `getByRole`
  // match ambiguous.
  const header = page.locator('header')
  const abortTrigger = header.getByRole('button', { name: 'Abort' })
  await expect(abortTrigger).toBeEnabled()
  await abortTrigger.click()

  const dialog = page.getByRole('alertdialog')
  await expect(dialog).toBeVisible()
  await expect(dialog.getByText('Abort this session?')).toBeVisible()
  await dialog.getByRole('button', { name: 'Abort' }).click()

  await expect(phaseBadge(page)).toHaveText('Aborted')
  await expect(page.getByText('Task complete')).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: 'Start new session' }),
  ).toBeVisible()

  // Aborting is a one-way, terminal transition -- the trigger itself
  // is disabled once `need === "done"` (`Controls`'s own `canAbort`
  // gate), not just inert to a second click.
  await expect(abortTrigger).toBeDisabled()
})
