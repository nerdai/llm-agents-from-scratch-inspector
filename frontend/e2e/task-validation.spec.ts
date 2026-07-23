import { expect, test } from '@playwright/test'
import { createSession, hailstoneTask } from './helpers'

/**
 * Non-empty Task validation, frontend side (backend's own is covered
 * by `test_create_session.py`'s `test_blank_task_returns_422` /
 * `test_blank_task_raises_session_config_error`). `TaskForm`'s
 * `canSubmit = task.trim().length > 0 && !disabled` disables "Create
 * session" for a blank/whitespace-only task -- this exercises that on
 * both the pre-session form and the post-completion one (#88),
 * which feeds the same validation through `initialTask`/`nextTaskDraft`.
 */
test('Create session is disabled for a blank or whitespace-only task', async ({
  page,
}) => {
  await page.goto('/')

  const taskBox = page.locator('#task-input')
  const createButton = page.getByRole('button', { name: 'Create session' })

  // Pre-filled by default_task -- enabled to start.
  await expect(createButton).toBeEnabled()

  await taskBox.fill('')
  await expect(createButton).toBeDisabled()

  await taskBox.fill('   ')
  await expect(createButton).toBeDisabled()

  await taskBox.fill('a real task')
  await expect(createButton).toBeEnabled()
})

test('Start new session carries a blank task forward as disabled, not a crash', async ({
  page,
}) => {
  await createSession(page, hailstoneTask(4))

  const header = page.locator('header')
  await header.getByRole('button', { name: 'Abort' }).click()
  const dialog = page.getByRole('alertdialog')
  await dialog.getByRole('button', { name: 'Abort' }).click()

  // Clear the reappeared, editable task box before starting a
  // fresh session -- nothing here should let a blank task through.
  await page.locator('#task-input').fill('')
  await page.getByRole('button', { name: 'Start new session' }).click()

  await expect(
    page.getByRole('button', { name: 'Create session' }),
  ).toBeDisabled()
})
