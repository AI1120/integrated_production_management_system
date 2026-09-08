import { Component, type ErrorInfo, type ReactNode } from 'react'

interface State {
  error: Error | null
}

/**
 * Last line of defence against a white screen.
 *
 * Without this, any throw during render unmounts the whole tree and leaves an
 * empty <div id="root">, with the only clue in a console the operator will
 * never open. A blank screen on a shop floor is indistinguishable from a dead
 * server, so it must never be the failure mode.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('IPMS crashed while rendering:', error, info.componentStack)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <div className="login-page">
        <div className="login-card">
          <div className="card">
            <div className="card-body">
              <h1 style={{ marginBottom: 6 }}>Something broke on this screen</h1>
              <p className="secondary" style={{ marginBottom: 14 }}>
                The rest of IPMS is still running. Production data is unaffected — nothing is saved
                from a screen that failed to draw.
              </p>
              <pre
                style={{
                  background: 'var(--surface-2)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)',
                  padding: 12,
                  fontSize: 12,
                  overflowX: 'auto',
                  marginBottom: 16,
                  whiteSpace: 'pre-wrap',
                }}
              >
                {error.message || String(error)}
              </pre>
              <div className="row">
                <button className="primary" onClick={() => this.setState({ error: null })}>
                  Try again
                </button>
                <button onClick={() => location.assign('/')}>Back to dashboard</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }
}
