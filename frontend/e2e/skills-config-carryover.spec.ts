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

/**
 * The Task field gets the same "reappear editable, carry forward"
 * treatment: once a session is done, it becomes a real
 * `Textarea` (pre-filled from that session's own task) instead of a
 * read-only `<p>`, and an edit made there is what "Start new session"
 * seeds the next `TaskForm` mount with.
 */
test('editing the task after abort carries the edit into the next session form', async ({
  page,
}) => {
  const task = hailstoneTask(4)
  await createSession(page, task)

  const header = page.locator('header')
  await header.getByRole('button', { name: 'Abort' }).click()
  const dialog = page.getByRole('alertdialog')
  await dialog.getByRole('button', { name: 'Abort' }).click()

  // Reappeared as a real, editable textbox, pre-filled from the
  // session that just finished -- not read-only text. Same `#task-
  // input` id as the pre-session form's own field (the two are
  // mutually exclusive in the DOM -- `hasSession`/`isDone` gate which
  // branch renders), so one selector works for both.
  const taskBox = page.locator('#task-input')
  await expect(taskBox).toHaveValue(task)
  await expect(taskBox).toBeEditable()

  await taskBox.fill('A brand new task for the next session.')

  await page.getByRole('button', { name: 'Start new session' }).click()

  // Back on the pre-session form -- the edit is still there, not
  // reset back to the original task or the script's default_task.
  await expect(
    page.getByRole('button', { name: 'Create session' }),
  ).toBeVisible()
  await expect(page.locator('#task-input')).toHaveValue(
    'A brand new task for the next session.',
  )
})

/**
 * An explicit-only skill left as an *uncommitted draft* (never
 * pressed Enter/comma, never blurred) at the moment "Create session"
 * is clicked -- `TaskForm`'s `handleSubmit` calls `commitPendingDraft()`
 * to fold it into the submitted `explicit_only_skills` either way, but
 * regression-tests that this also actually commits the draft into
 * `useSkillsConfig()`'s own state (not just the value sent to the
 * backend). Since that hook now persists for `ConfigRail`'s whole
 * lifetime (#88), a draft folded into the request but never committed
 * to state would otherwise vanish -- neither shown as a real tag nor
 * carried into the next session -- even though it was genuinely used.
 */
test('an uncommitted skill draft at submit time still shows as a real tag afterward', async ({
  page,
}) => {
  await page.goto('/')
  await page.locator('#task-input').fill(hailstoneTask(4))
  await page.getByPlaceholder('skill-name…').fill('draft-skill')
  // No Enter/comma, no blur -- straight to submit with the draft
  // still sitting in the input.
  await page.getByRole('button', { name: 'Create session' }).click()
  await expect(page).toHaveURL(/session=/)

  const header = page.locator('header')
  await header.getByRole('button', { name: 'Abort' }).click()
  const dialog = page.getByRole('alertdialog')
  await dialog.getByRole('button', { name: 'Abort' }).click()

  // The draft is now a real, committed tag -- not stuck as leftover
  // uncommitted text in the reappeared input.
  await expect(
    page.getByRole('button', { name: 'Remove draft-skill' }),
  ).toBeVisible()
  // The placeholder itself disappears once a real tag exists
  // (`explicitSkills.length === 0 ? 'skill-name…' : ''`), so the
  // stable id is what's checked here, not the placeholder text.
  await expect(page.locator('#explicit-skills-input')).toHaveValue('')
})
