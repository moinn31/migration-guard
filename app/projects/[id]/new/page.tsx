'use client'

import { useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { AppShell, PageHeader } from '@/components/app-shell'
import { api } from '@/lib/api/client'

export default function NewRunPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const [url, setUrl] = useState('')
  const [mode, setMode] = useState('minimal')
  const [message, setMessage] = useState('')
  async function submit() {
    const { data, error } = await api.POST('/projects/{project_id}/runs', { params: { path: { project_id: id } } })
    if (error || !data) setMessage('Unable to start the run.')
    else router.push(`/runs/${data.id}`)
  }
  return <AppShell><PageHeader eyebrow="New verification" title="Migration wizard" /><div className="mx-auto max-w-3xl space-y-6 p-6 lg:p-10"><section className="rounded-2xl border border-white/[0.08] bg-white/[0.035] p-6"><p className="text-xs uppercase tracking-widest text-cyan-300">Step 1 · Repository</p><label className="mt-5 block text-sm text-slate-300">GitHub HTTPS URL<input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://github.com/org/repository" className="mt-2 w-full rounded-xl border border-white/10 bg-black/20 px-3 py-3 text-white" /></label><label className="mt-4 block text-sm text-slate-300">Or upload a zip<input type="file" accept=".zip" className="mt-2 block w-full rounded-xl border border-dashed border-white/15 p-4 text-sm text-slate-500" /></label></section><section className="rounded-2xl border border-white/[0.08] bg-white/[0.035] p-6"><p className="text-xs uppercase tracking-widest text-cyan-300">Step 2 · Target</p><p className="mt-4 text-sm text-slate-300">Detected target: Java 17</p><div className="mt-4 grid gap-3 sm:grid-cols-2">{['minimal', 'maximal'].map((value) => <button key={value} onClick={() => setMode(value)} className={`rounded-xl border p-4 text-left ${mode === value ? 'border-cyan-300/50 bg-cyan-300/10' : 'border-white/10'}`}><p className="font-medium text-white capitalize">{value} migration</p><p className="mt-1 text-xs text-slate-500">{value === 'minimal' ? 'Smallest deterministic change set.' : 'Apply all compatible upgrade recipes.'}</p></button>)}</div></section>{message && <p className="text-sm text-red-300">{message}</p>}<button onClick={submit} className="rounded-xl bg-cyan-300 px-5 py-3 font-semibold text-slate-950">Start verification</button></div></AppShell>
}
