import { expect, test } from '@playwright/test'
import { createSession, hailstoneTask } from './helpers'

/**
 * Skills Scope / Explicit-only Skills carry-over across "Start new
 * session" (#88).
 *
 * Once a session is done (aborted or completed), those two config
 * inputs reappear in the rail -- same position as the pre-session
 * form -- so an operator can set up the *next* session's skill config
 * while still looking at the one that just finished. `ConfigRail`
 * owns a single `useSkillsConfig()` instance across that transition
 * (see its docstring), so whatever was picked there should still be
 * selected once "Start new session" mounts a fresh pre-session form,
 * not reset back to nothing.
 */
test('scope/explicit-only choices made after abort persist into the next session form', async ({
  page,
}) => {
  await createSession(page, hailstoneTask(4))

  const header = page.locator('header')
  await header.getByRole('button', { name: 'Abort' }).click()
  const dialog = page.getByRole('alertdialog')
  await dialog.getByRole('button', { name: 'Abort' }).click()

  // Reappeared, interactive, and currently unset.
  const projectScope = page.getByRole('button', { name: 'project' })
  await expect(projectScope).toBeVisible()
  await expect(projectScope).toHaveAttribute('aria-pressed', 'false')

  // Pick a scope and add an explicit-only skill for the *next* session.
  await projectScope.click()
  await expect(projectScope).toHaveAttribute('aria-pressed', 'true')
  const skillInput = page.getByPlaceholder('skill-name…')
  await skillInput.fill('my-skill')
  await skillInput.press('Enter')
  await expect(
    page.getByRole('button', { name: 'Remove my-skill' }),
  ).toBeVisible()

  await page.getByRole('button', { name: 'Start new session' }).click()

  // Back on the pre-session form -- the same choices are still there.
  await expect(
    page.getByRole('button', { name: 'Create session' }),
  ).toBeVisible()
  const projectScopeAgain = page.getByRole('button', { name: 'project' })
  await expect(projectScopeAgain).toHaveAttribute('aria-pressed', 'true')
  await expect(
    page.getByRole('button', { name: 'Remove my-skill' }),
  ).toBeVisible()
})
