import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// `agent-inspector launch --dev` sets this to the backend's actual
// `--port` when it spawns this dev server, so the proxy target always
// matches regardless of the port chosen (defaults to 8000 to match
// the CLI's own default when run standalone via `npm run dev`).
const backendPort = process.env.AGENT_INSPECTOR_BACKEND_PORT ?? '8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      // `__dirname` is undefined here: this file loads as ESM (Vite 8
      // + `package.json`'s `"type": "module"`), so the alias target
      // is resolved from `import.meta.url` instead.
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // Explicit IPv4 loopback, not Vite's default `localhost` -- on at
    // least one real environment (GitHub Actions' `ubuntu-latest`
    // runners, hit while wiring up the Playwright E2E suite's CI job,
    // see #62), Node resolves the bare hostname `localhost` to the
    // IPv6 loopback only, so a client connecting to the IPv4
    // `127.0.0.1` `cli.py`'s own `browser_url` and this suite's
    // `playwright.config.ts` both use can never reach it, even though
    // Vite itself reports "ready". Binding explicitly keeps dev-server
    // reachability consistent across environments instead of
    // depending on how a given machine resolves `localhost`.
    host: '127.0.0.1',
    // In `agent-inspector launch --dev`, the FastAPI backend fronts
    // the API while this dev server fronts the UI; proxying /api
    // keeps both reachable from a single origin during development.
    proxy: {
      '/api': `http://127.0.0.1:${backendPort}`,
    },
  },
})
