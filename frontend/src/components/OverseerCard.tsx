interface OverseerCardProps {
  n: number
  outcome: 'next_step' | 'final_result'
  decision?: unknown
  instruction?: string
}

function formatDecision(decision: unknown): string {
  if (decision === null || decision === undefined) return ''
  if (typeof decision === 'string') return decision
  try {
    return JSON.stringify(decision, null, 2)
  } catch {
    return String(decision)
  }
}

function OverseerCard({
  n,
  outcome,
  decision,
  instruction,
}: OverseerCardProps) {
  const decisionText = formatDecision(decision)
  return (
    <article className="call-card call-overseer">
      <header className="call-header">
        <span className="call-index">#{n}</span>
        <span className="role-pill role-overseer">overseer</span>
        <code className="call-op">get_next_step()</code>
      </header>
      <div className="call-body">
        {decisionText && (
          <div className="kv">
            <span className="kv-label">decision</span>
            <pre className="kv-value">{decisionText}</pre>
          </div>
        )}
        {outcome === 'next_step' ? (
          <div className="kv">
            <span className="kv-label">next step</span>
            <p className="kv-value instruction">{instruction}</p>
          </div>
        ) : (
          <p className="final-flag">
            kind = final_result — task objective reached
          </p>
        )}
      </div>
    </article>
  )
}

export default OverseerCard
