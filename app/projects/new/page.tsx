'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { AppShell, PageHeader } from '@/components/app-shell'
import { api } from '@/lib/api/client'

export default function NewProjectPage() {
  const router = useRouter()
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  async function submit() {
    const { data } = await api.POST('/projects', { body: { name, repository_url: url || null } })
    if (data) router.push(`/projects/${data.id}/new`)
    else setError('Unable to create project.')
  }
  return <AppShell><PageHeader eyebrow="Workspace" title="New project" /><div className="max-w-2xl space-y-4 p-6 lg:p-10"><label className="block text-sm text-slate-400">Project name<input value={name} onChange={(e) => setName(e.target.value)} className="mt-2 w-full rounded-xl border border-white/10 bg-black/20 p-3 text-white" /></label><label className="block text-sm text-slate-400">Repository URL<input value={url} onChange={(e) => setUrl(e.target.value)} className="mt-2 w-full rounded-xl border border-white/10 bg-black/20 p-3 text-white" placeholder="https://github.com/org/repo" /></label>{error && <p className="text-sm text-red-300">{error}</p>}<button onClick={submit} disabled={!name} className="rounded-xl bg-cyan-300 px-4 py-2.5 font-semibold text-slate-950 disabled:opacity-40">Continue</button></div></AppShell>
}
