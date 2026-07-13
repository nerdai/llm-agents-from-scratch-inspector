import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // In `agent-inspector launch --dev`, the FastAPI backend runs on
    // port 8000 while this dev server fronts the UI; proxying /api
    // keeps both reachable from a single origin during development.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
