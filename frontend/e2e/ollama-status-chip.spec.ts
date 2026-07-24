import { expect, test } from '@playwright/test'

/**
 * `OllamaStatusChip` for a non-Ollama-backed agent (see #90).
 *
 * `fixtures/scripted_agent.py`'s `_StatelessHailstoneLLM` isn't an
 * `OllamaLLM` -- `GET /api/agent-info`'s `is_local_ollama` is `null`
 * for it, same as any other non-Ollama `BaseLLM` implementation (the
 * framework also ships an OpenAI one). The chip should read "not
 * ollama", not a stale/misleading "ollama offline" -- there's no local
 * daemon to be offline from in the first place.
 *
 * The cloud case (`is_local_ollama: false`, a real `OllamaLLM(host=
 * "https://ollama.com", ...)`) is covered by backend tests
 * (`test_agent_info.py`'s `TestOllamaHostDetection`) rather than here
 * -- exercising it live would need a second Playwright project/
 * webServer just for this one chip state.
 */
test('shows "not ollama" for a non-Ollama-backed agent, not a stale "offline"', async ({
  page,
}) => {
  await page.goto('/')

  const header = page.locator('header')
  await expect(header.getByText('not ollama', { exact: true })).toBeVisible()
  await expect(header.getByText('ollama offline')).toHaveCount(0)
})
