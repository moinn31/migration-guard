import createClient from 'openapi-fetch'
import type { paths } from '@/lib/api/generated/schema'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000'
const TOKEN_KEY = 'migrationguard.access_token'

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null) {
  if (typeof window === 'undefined') return
  if (token) window.localStorage.setItem(TOKEN_KEY, token)
  else window.localStorage.removeItem(TOKEN_KEY)
}

export async function getActiveToken(): Promise<string | null> {
  if (typeof window === 'undefined') return null

  // 1. Check if Clerk session is available
  const clerk = (window as unknown as { Clerk?: { session?: { getToken: () => Promise<string | null> } } }).Clerk
  if (clerk?.session) {
    try {
      const clerkToken = await clerk.session.getToken()
      if (clerkToken) return clerkToken
    } catch {
      // Fallback to local token
    }
  }

  // 2. Fallback to localStorage token
  return getToken()
}

export const api = createClient<paths>({
  baseUrl: API_URL,
  fetch: async (request: Request) => {
    const headers = new Headers(request.headers)
    const token = await getActiveToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    headers.set('Content-Type', headers.get('Content-Type') ?? 'application/json')
    const response = await fetch(request, { headers })
    if (response.status === 401 && typeof window !== 'undefined') {
      setToken(null)
      window.dispatchEvent(new CustomEvent('migrationguard:unauthorized'))
    }
    return response
  },
})

export function clearToken() {
  setToken(null)
}
