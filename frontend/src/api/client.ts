import axios, { AxiosError } from 'axios'

export const TOKEN_KEY = 'ipms.token'

/**
 * In dev, '/api' is same-origin and Vite proxies it to the backend. A production
 * build has no proxy, so set VITE_API_BASE at build time when the API is not
 * served from the same origin as the app.
 */
export const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

export const api = axios.create({ baseURL: API_BASE })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

/** A 401 anywhere means the session is gone - drop the token and bounce to login. */
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401 && !error.config?.url?.endsWith('/auth/login')) {
      localStorage.removeItem(TOKEN_KEY)
      if (location.pathname !== '/login') location.assign('/login')
    }
    return Promise.reject(error)
  },
)

/** Pull the human-readable message out of a FastAPI error response. */
export function errorMessage(error: unknown, fallback = 'Something went wrong'): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      // Pydantic validation errors arrive as a list of {loc, msg}.
      return detail
        .map((entry: { loc?: unknown[]; msg?: string }) => {
          const field = Array.isArray(entry.loc) ? entry.loc.slice(1).join('.') : ''
          return field ? `${field}: ${entry.msg}` : entry.msg
        })
        .filter(Boolean)
        .join('; ')
    }
    if (error.code === 'ERR_NETWORK' || error.code === 'ECONNABORTED') {
      return 'Cannot reach the IPMS server.'
    }
    // With the dev proxy in front, a dead backend surfaces as a bodyless 500
    // from Vite rather than a network error - detail is absent in that case.
    if (error.response?.status === 500 && detail === undefined) {
      return 'Cannot reach the IPMS server. Is the backend running on port 8010?'
    }
    return error.message || fallback
  }
  return error instanceof Error ? error.message : fallback
}
