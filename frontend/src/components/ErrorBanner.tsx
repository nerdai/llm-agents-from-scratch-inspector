import type { ApiErrorInfo } from '../session/types'

interface ErrorBannerProps {
  error: ApiErrorInfo
}

/**
 * A minimal, inline surfacing of a failed request's normalized
 * `{status, detail}` shape (see `api/client.ts`'s `ApiError`). #23
 * owns the real toast UI; this only proves the shape reaches a
 * component at all.
 */
function ErrorBanner({ error }: ErrorBannerProps) {
  return (
    <div
      className="rounded-lg border border-destructive/40 bg-destructive/10 px-3.5 py-2.5 text-sm text-destructive"
      role="alert"
    >
      <strong>
        Request failed{error.status ? ` (HTTP ${error.status})` : ''}:
      </strong>{' '}
      {error.detail}
    </div>
  )
}

export default ErrorBanner
