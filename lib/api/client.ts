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

export async function getActiveToken(options: { skipCache?: boolean } = {}): Promise<string | null> {
  if (typeof window === 'undefined') return null

  // 1. Check if Clerk session is available
  const clerk = (window as unknown as { Clerk?: { session?: { getToken: (options?: { skipCache?: boolean }) => Promise<string | null> } } }).Clerk
  if (clerk?.session) {
    try {
      return await clerk.session.getToken(options)
    } catch {
      return null
    }
  }

  // A signed-out/loading Clerk session must not reuse an old local JWT.
  if (clerk) return null
  return getToken()
}

export async function authenticatedFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const template = input instanceof Request ? input.clone() : input
  const send = async (refresh: boolean) => {
    const headers = new Headers(init.headers ?? (template instanceof Request ? template.headers : undefined))
    const token = await getActiveToken({ skipCache: refresh })
    if (token) headers.set('Authorization', `Bearer ${token}`)
    else headers.delete('Authorization')
    return fetch(template instanceof Request ? template.clone() : template, { ...init, headers })
  }
  let response = await send(false)
  if (response.status === 401) response = await send(true)
  if (response.status === 401 && typeof window !== 'undefined') {
    setToken(null)
    window.dispatchEvent(new CustomEvent('migrationguard:unauthorized'))
  }
  return response
}

export const api = createClient<paths>({
  baseUrl: API_URL,
  fetch: async (request: Request) => {
    return authenticatedFetch(request)
  },
})

export function clearToken() {
  setToken(null)
}
