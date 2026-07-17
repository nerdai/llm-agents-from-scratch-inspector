import { expect, test } from '@playwright/test'
import {
  clickGetNextStep,
  clickRunStep,
  createSession,
  hailstoneTask,
} from './helpers'

/**
 * The Templates and Rollout panels, verifying they render *real* data
 * from the backend once opened -- not just that the toggle affordance
 * exists. Both moved out of overlay `Sheet` drawers into persistent
 * panels during the theme-overhaul cycle (`TemplatesSection.tsx`, a
 * vertical accordion in the config rail; `RolloutPanel.tsx`, a
 * collapsible panel docked to the right edge of the main content
 * area) -- see this issue's refinement comment.
 */

test('Templates section renders the framework default templates', async ({
  page,
}) => {
  // Not session-scoped -- available before a session exists (see
  // `ConfigRail`/`TemplatesSection`'s own docstrings).
  await page.goto('/')

  await page.getByRole('button', { name: 'Templates' }).click()

  // `GET /api/templates` returns all 11 `LLMAgentTemplates` keys;
  // spot-check a representative few by their labels
  // (`TemplatesSection.tsx`'s `TEMPLATE_LABELS`) rather than every one.
  await expect(page.getByText('system_message', { exact: true })).toBeVisible()
  await expect(page.getByText('get_next_step', { exact: true })).toBeVisible()
  await expect(page.getByText('skills_catalog', { exact: true })).toBeVisible()

  // Real template *content*, not just the label -- proves the panel
  // actually rendered `GET /api/templates`'s response, not an empty
  // shell. A single-line fragment of `DEFAULT_SYSTEM_MESSAGE` (kept
  // clear of its own `\n` breaks, which the Shiki-highlighted block
  // renders as real line breaks that could otherwise split the match).
  await expect(
    page.getByText('You are a helpful assistant working through problems'),
  ).toBeVisible()
})

test('Rollout panel renders the session rollout once a step has run', async ({
  page,
}) => {
  const task = hailstoneTask(4)
  await createSession(page, task)
  await clickGetNextStep(page)
  await clickRunStep(page)

  const rolloutTab = page.getByRole('button', { name: /rollout/i })
  await expect(rolloutTab).toBeVisible()
  await rolloutTab.click()

  // Scoped to the panel's own content container -- `Timeline` renders
  // its own, unrelated "Step 1" trigger row label at the same time, so
  // an unscoped match would be ambiguous.
  const panel = page.locator('#rollout-panel-content')
  await expect(
    panel.getByRole('heading', { name: 'Session rollout' }),
  ).toBeVisible()
  await expect(panel.getByText('Step 1', { exact: true })).toBeVisible()
  // `RolloutPanel.splitRolloutSteps` strips the raw
  // `=== Task Step Start/End ===` markers themselves before rendering
  // (see that function's docstring) -- assert on real content from
  // *inside* the step instead: the framework's own
  // `step_rollout_content_instruction` template wraps the executed
  // step's instruction, which for this suite's first (deterministic)
  // step is the task instruction verbatim.
  await expect(
    panel.getByText(`My current instruction is '${task}'`),
  ).toBeVisible()
})
