import { useState, type FormEvent } from 'react'

import { errorMessage } from '../api/client'
import { Alert, Card, Field } from '../components/ui'
import { useAuth } from '../lib/auth'

const DEMO_USERS = [
  { username: 'planner', password: 'planner123', role: 'Planner' },
  { username: 'operator1', password: 'oper123', role: 'Operator' },
  { username: 'qc1', password: 'qc123', role: 'Quality' },
  { username: 'wh1', password: 'wh123', role: 'Warehouse' },
  { username: 'admin', password: 'admin123', role: 'Admin' },
]

export function Login() {
  const { signIn } = useAuth()
  const [username, setUsername] = useState('planner')
  const [password, setPassword] = useState('planner123')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await signIn(username, password)
    } catch (exception) {
      setError(errorMessage(exception, 'Sign in failed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <Card>
          <div className="login-head">
            <div className="mark">IPMS</div>
            <div className="sub">Integrated Production Management System</div>
          </div>

          <form onSubmit={submit} className="stack" style={{ gap: 12 }}>
            {error && <Alert tone="error">{error}</Alert>}
            <Field label="Username">
              <input
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                autoFocus
                required
              />
            </Field>
            <Field label="Password">
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                required
              />
            </Field>
            <button className="primary" type="submit" disabled={busy} style={{ justifyContent: 'center' }}>
              {busy ? 'Signing in...' : 'Sign in'}
            </button>
          </form>

          <div className="demo-users">
            <div className="t">Sample accounts</div>
            <div className="stack" style={{ gap: 4 }}>
              {DEMO_USERS.map((account) => (
                <button
                  key={account.username}
                  className="u"
                  type="button"
                  onClick={() => {
                    setUsername(account.username)
                    setPassword(account.password)
                  }}
                >
                  <span className="code">{account.username}</span>
                  <span className="muted small">{account.role}</span>
                </button>
              ))}
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}
