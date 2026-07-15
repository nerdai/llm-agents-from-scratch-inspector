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
    // In `agent-inspector launch --dev`, the FastAPI backend fronts
    // the API while this dev server fronts the UI; proxying /api
    // keeps both reachable from a single origin during development.
    proxy: {
      '/api': `http://127.0.0.1:${backendPort}`,
    },
  },
})
