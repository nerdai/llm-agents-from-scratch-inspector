import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, devices } from '@playwright/test'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// `frontend/` -> repo root, one level up. `webServer.command` below is
// run from there (see `cwd`) so it can invoke `agent-inspector` (a
// `uv`-managed console script rooted at the repo's own `pyproject.toml`)
// without needing an absolute path.
const REPO_ROOT = path.resolve(__dirname, '..')

// A fixed, unlikely-to-collide port for the backend this suite drives
// (distinct from `agent-inspector launch`'s own default of 8000, so a
// developer's own manually-launched instance never collides with the
// suite's). `--dev` (below) always serves the UI on Vite's own fixed
// default port (5173, see `cli.py`'s `DEFAULT_VITE_PORT`), regardless
// of this value -- this only picks the *backend* API's port.
const BACKEND_PORT = 8931

// The UI origin the suite actually drives: `agent-inspector launch
// --dev` starts the FastAPI backend on `BACKEND_PORT` *and* spawns the
// frontend's own Vite dev server (proxying `/api` back to that backend
// -- see `vite.config.ts`), serving the UI at this fixed dev-server
// origin. Deliberately not a `npm run build` + `serve_static` single
// origin: that would require staging built assets under
// `src/agent_inspector/web/` before every run (mirroring the
// hatchling build hook) as an extra, easy-to-forget step -- `--dev` is
// the one-command path already documented for local development, so
// this suite exercises exactly that.
const BASE_URL = 'http://127.0.0.1:5173'

/**
 * Playwright E2E suite configuration (issue #62).
 *
 * Drives a real FastAPI backend -- not mocked -- but with no live
 * Ollama dependency: `webServer.command` launches
 * `frontend/e2e/fixtures/scripted_agent.py`'s `agent_builder`, whose
 * backbone LLM is a scripted, network-free `BaseLLM` double (see that
 * file's docstring for why it's *stateless* rather than a consumed
 * script, unlike `tests/test_integration_loop.py`'s `_SequencedLLM`).
 *
 * `webServer` (rather than a custom `globalSetup`/`globalTeardown`)
 * because Playwright's own built-in "run a shell command, poll a URL
 * until it's up, tear it down after the run" mechanism already covers
 * exactly this shape -- `agent-inspector launch` is one long-running
 * foreground process (backend + a spawned Vite dev server child, torn
 * down together on SIGTERM -- see `cli.py`'s `finally` block), not
 * something that needs custom orchestration.
 */
export default defineConfig({
  testDir: './e2e',
  testIgnore: ['**/fixtures/**'],
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command:
      'uv run agent-inspector launch ' +
      'frontend/e2e/fixtures/scripted_agent.py ' +
      `--no-open --dev --port ${BACKEND_PORT}`,
    cwd: REPO_ROOT,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    // `uv sync`ing the backend (first run) + Vite's cold start can
    // both take a while, especially in a fresh CI checkout.
    timeout: 120_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
})
