import type {
  CompleteResponse,
  CreateSessionRequest,
  CreateSessionResponse,
  NextStepResponse,
  RunStepResponse,
} from './types'

/**
 * Thin fetch wrapper around the `/api/sessions/*` contract.
 *
 * The Vite dev server proxies `/api` to the FastAPI backend (see
 * vite.config.ts), so these calls work unmodified in dev and in the
 * built `agent-inspector launch` bundle alike -- no base URL or mock
 * layer needed.
 */

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function extractErrorMessage(res: Response): Promise<string> {
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
    throw new ApiError(res.status, await extractErrorMessage(res))
  }

  return (await res.json()) as T
}

export function createSession(
  body: CreateSessionRequest,
): Promise<CreateSessionResponse> {
  return request<CreateSessionResponse>('/api/sessions', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function fetchNextStep(sessionId: string): Promise<NextStepResponse> {
  return request<NextStepResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/next-step`,
    { method: 'POST' },
  )
}

export function runStep(sessionId: string): Promise<RunStepResponse> {
  return request<RunStepResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/run-step`,
    { method: 'POST' },
  )
}

export function completeSession(sessionId: string): Promise<CompleteResponse> {
  return request<CompleteResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/complete`,
    { method: 'POST' },
  )
}
