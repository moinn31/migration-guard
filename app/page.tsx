'use client'

import { FormEvent, useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import { api, setToken } from '@/lib/api/client'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  async function login(event: FormEvent) {
    event.preventDefault(); setLoading(true); setError(null)
    const { data, error: responseError } = await api.POST('/auth/login', { body: { email, password, role: 'developer' } })
    if (responseError || !data) setError('Sign in failed. Check your credentials.')
    else { setToken(data.access_token); window.location.href = '/dashboard' }
    setLoading(false)
  }
  return <main className="flex min-h-screen items-center justify-center px-5"><form onSubmit={login} className="w-full max-w-md rounded-3xl border border-white/[0.08] bg-white/[0.04] p-8 shadow-2xl"><div className="flex items-center gap-3"><span className="flex size-11 items-center justify-center rounded-xl bg-cyan-300 text-slate-950"><ShieldCheck /></span><div><h1 className="text-xl font-semibold text-white">Migration<span className="text-cyan-300">Guard</span></h1><p className="text-xs text-slate-500">Evidence-led Java migration verification</p></div></div><h2 className="mt-10 text-2xl font-semibold text-white">Sign in</h2><label className="mt-6 block text-sm text-slate-400">Email<input className="mt-2 w-full rounded-xl border border-white/10 bg-black/20 px-3 py-3 text-white outline-none focus:border-cyan-300" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label><label className="mt-4 block text-sm text-slate-400">Password<input className="mt-2 w-full rounded-xl border border-white/10 bg-black/20 px-3 py-3 text-white outline-none focus:border-cyan-300" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>{error && <p className="mt-4 text-sm text-red-300">{error}</p>}<button disabled={loading} className="mt-6 w-full rounded-xl bg-cyan-300 px-4 py-3 font-semibold text-slate-950 disabled:opacity-50">{loading ? 'Signing in…' : 'Sign in'}</button></form></main>
}
