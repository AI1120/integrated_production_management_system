import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import { api, TOKEN_KEY } from '../api/client'
import type { Role, User } from '../api/types'

interface AuthState {
  user: User | null
  loading: boolean
  signIn: (username: string, password: string) => Promise<void>
  signOut: () => void
  can: (...roles: Role[]) => boolean
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  // Restore the session on load; a stale token resolves to signed-out.
  useEffect(() => {
    if (!localStorage.getItem(TOKEN_KEY)) {
      setLoading(false)
      return
    }
    api
      .get<User>('/auth/me')
      .then((response) => setUser(response.data))
      .catch((error) => {
        // Only an actual rejection invalidates the token. Dropping it on a
        // network error would sign the operator out every time the backend
        // restarts, losing their place mid-shift.
        const status = (error as { response?: { status?: number } })?.response?.status
        if (status === 401 || status === 403) localStorage.removeItem(TOKEN_KEY)
      })
      .finally(() => setLoading(false))
  }, [])

  const signIn = useCallback(async (username: string, password: string) => {
    const { data } = await api.post<{ access_token: string; user: User }>('/auth/login', { username, password })
    localStorage.setItem(TOKEN_KEY, data.access_token)
    setUser(data.user)
  }, [])

  const signOut = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setUser(null)
  }, [])

  // ADMIN passes every gate, mirroring require_roles() on the server.
  const can = useCallback(
    (...roles: Role[]) => !!user && (user.role === 'ADMIN' || roles.includes(user.role)),
    [user],
  )

  const value = useMemo(() => ({ user, loading, signIn, signOut, can }), [user, loading, signIn, signOut, can])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
