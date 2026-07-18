import { expect, test } from '@playwright/test'
import { hailstoneTask } from './helpers'

/**
 * `GET /api/agent-info` (#86): the discovered agent's static
 * properties -- model, tools, and an optional default_task -- shown
 * in the config rail *before* any session exists, unlike skills
 * (session-only, since they depend on per-session `skills_scopes`/
 * `explicit_only_skills`).
 *
 * `fixtures/scripted_agent.py` sets a real `model` attribute and a
 * `default_task` matching `hailstoneTask(4)` exactly, so this can
 * assert on real values from the backend rather than just "some text
 * is present".
 */
test('pre-session rail shows the discovered model, tools, and default task', async ({
  page,
}) => {
  await page.goto('/')

  // The task field is pre-filled from the script's `default_task`,
  // not left blank or hardcoded in the frontend.
  await expect(page.locator('#task-input')).toHaveValue(hailstoneTask(4))

  // Model/Tools render under the "LLM Agent" heading, grouped with
  // Templates -- same as the post-session ConfigRail branch.
  await expect(page.getByText('LLM Agent', { exact: true })).toBeVisible()
  await expect(page.getByText('scripted-test-llm')).toBeVisible()
  await expect(page.getByText('next_number', { exact: true })).toBeVisible()
})
