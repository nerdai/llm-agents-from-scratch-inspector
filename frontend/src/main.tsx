import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider } from 'next-themes'
import './index.css'
import App from './App.tsx'

// One QueryClient for the whole app. Mutation results aren't cached by
// key the way query results are, so the defaults here only really
// govern the GET-backed hooks (`useHealth`, `useOllamaStatus`,
// `useSessionState`, `useRollout`, `useTemplates`); `retry: false`
// keeps a 404/409 from a stale session id from silently retrying
// against a backend that will keep saying no.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
