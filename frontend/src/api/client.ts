import type {
  AbortSessionResponse,
  CompleteResponse,
  CreateSessionRequest,
  CreateSessionResponse,
  EditResultRequest,
  EditResultResponse,
  EditStepRequest,
  EditStepResponse,
  HealthResponse,
  NextStepResponse,
  OllamaStatusResponse,
  RejectRequest,
  RejectResponse,
  RolloutResponse,
  RunStepResponse,
  SessionStateResponse,
  TemplatesOut,
} from './types'

/**
 * Thin fetch wrapper around the Agent Inspector HTTP API (see
 * `src/agent_inspector/routes/*.py`).
 *
 * The Vite dev server proxies `/api` to the FastAPI backend (see
 * vite.config.ts), so these calls work unmodified in dev and in the
 * built `agent-inspector launch` bundle alike -- no base URL or mock
 * layer needed. Each function here does exactly one HTTP call; the
 * `useQuery`/`useMutation` hooks in `api/hooks/` are the layer that
 * gives each of these a cache key / lifecycle (see that directory).
 */

/**
 * A normalized `{status, detail}` view of a failed request.
 *
 * `status` is `0` for a request that never reached the server (e.g. a
 * network error). `detail` mirrors FastAPI's own `HTTPException.detail`
 * -- a plain string in every case the backend raises today (404/409/
 * 422/500/502, see each route's docstring) -- so error-surfacing UI
 * (#23) can render it directly without re-parsing the response body.
 */
export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function extractErrorDetail(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json()
    if (body && typeof body === 'object' && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail
      if (typeof detail === 'string') return detail
      if (detail !== undefined) return JSON.stringify(detail)
    }
  } catch {
    // response body wasn't JSON (or was empty) -- fall through
  }
  return res.statusText || `Request failed with status ${res.status}`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    throw new ApiError(0, `Network error: ${message}`)
  }

  if (!res.ok) {
    throw new ApiError(res.status, await extractErrorDetail(res))
  }

  return (await res.json()) as T
}

function sessionPath(sessionId: string, suffix: string): string {
  return `/api/sessions/${encodeURIComponent(sessionId)}${suffix}`
}

// --- GET /api/health ---

export function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/api/health')
}

// --- GET /api/ollama/status ---

export function fetchOllamaStatus(): Promise<OllamaStatusResponse> {
  return request<OllamaStatusResponse>('/api/ollama/status')
}

// --- POST /api/sessions ---

export function createSession(
  body: CreateSessionRequest,
): Promise<CreateSessionResponse> {
  return request<CreateSessionResponse>('/api/sessions', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

// --- GET /api/sessions/{id} ---

export function fetchSessionState(
  sessionId: string,
): Promise<SessionStateResponse> {
  return request<SessionStateResponse>(sessionPath(sessionId, ''))
}

// --- GET /api/sessions/{id}/rollout ---

export function fetchRollout(sessionId: string): Promise<RolloutResponse> {
  return request<RolloutResponse>(sessionPath(sessionId, '/rollout'))
}

// --- GET /api/templates (not session-scoped) ---

export function fetchTemplates(): Promise<TemplatesOut> {
  return request<TemplatesOut>('/api/templates')
}

// --- POST /api/sessions/{id}/next-step ---

export function fetchNextStep(sessionId: string): Promise<NextStepResponse> {
  return request<NextStepResponse>(sessionPath(sessionId, '/next-step'), {
    method: 'POST',
  })
}

// --- POST /api/sessions/{id}/run-step ---

export function runStep(sessionId: string): Promise<RunStepResponse> {
  return request<RunStepResponse>(sessionPath(sessionId, '/run-step'), {
    method: 'POST',
  })
}

// --- PATCH /api/sessions/{id}/step ---

export function editStep(
  sessionId: string,
  body: EditStepRequest,
): Promise<EditStepResponse> {
  return request<EditStepResponse>(sessionPath(sessionId, '/step'), {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

// --- POST /api/sessions/{id}/complete ---

export function completeSession(sessionId: string): Promise<CompleteResponse> {
  return request<CompleteResponse>(sessionPath(sessionId, '/complete'), {
    method: 'POST',
  })
}

// --- PATCH /api/sessions/{id}/result ---

export function editResult(
  sessionId: string,
  body: EditResultRequest,
): Promise<EditResultResponse> {
  return request<EditResultResponse>(sessionPath(sessionId, '/result'), {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

// --- POST /api/sessions/{id}/abort ---

export function abortSession(sessionId: string): Promise<AbortSessionResponse> {
  return request<AbortSessionResponse>(sessionPath(sessionId, '/abort'), {
    method: 'POST',
  })
}

// --- POST /api/sessions/{id}/reject ---

export function rejectSession(
  sessionId: string,
  body: RejectRequest,
): Promise<RejectResponse> {
  return request<RejectResponse>(sessionPath(sessionId, '/reject'), {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
