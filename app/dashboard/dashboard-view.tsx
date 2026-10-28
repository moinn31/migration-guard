'use client'

import Link from 'next/link'
import { Plus, ShieldAlert, ShieldCheck, Timer, Workflow } from 'lucide-react'
import { AppShell, PageHeader } from '@/components/app-shell'
import { VerdictBadge } from '@/components/verdict-badge'
import { useProjects } from '@/lib/api/hooks'

export default function DashboardPage() {
  const projects = useProjects()
  const headerAction = <Link href="/projects/new" className="inline-flex items-center gap-2 rounded-xl bg-cyan-300 px-4 py-2.5 text-sm font-semibold text-slate-950"><Plus className="size-4" />New project</Link>
  const items = projects.data ?? []
  const cards: Array<[string, number, typeof Workflow]> = [['Projects', items.length, Workflow], ['Verified', 0, ShieldCheck], ['Needs review', 0, ShieldAlert], ['Active runs', 0, Timer]]
  return <AppShell><PageHeader eyebrow="Verification workspace" title="Dashboard" action={headerAction} /><div className="space-y-8 p-6 lg:p-10"><div className="grid gap-4 md:grid-cols-4">{cards.map(([label, value, Icon]) => <div key={label} className="rounded-2xl border border-white/[0.08] bg-white/[0.035] p-5"><Icon className="size-5 text-cyan-300" /><p className="mt-6 text-sm text-slate-400">{label}</p><p className="mt-1 text-3xl font-semibold text-white">{value}</p></div>)}</div>{projects.error && <p className="text-sm text-red-300">Unable to load projects. Check that the API is running.</p>}<section className="rounded-2xl border border-white/[0.08] bg-white/[0.035] p-6"><h2 className="text-lg font-semibold text-white">Recent projects</h2>{items.length === 0 ? <p className="py-12 text-center text-sm text-slate-500">No projects yet. Create one to start a verification run.</p> : <div className="mt-5 grid gap-3">{items.map((project) => <Link key={project.id} href={`/projects/${project.id}/new`} className="flex items-center justify-between rounded-xl border border-white/[0.06] p-4 hover:bg-white/[0.05]"><div><p className="font-medium text-white">{project.name}</p><p className="mt-1 text-xs text-slate-500">{project.repository_url || 'Zip upload project'}</p></div><VerdictBadge verdict="INCONCLUSIVE" /></Link>)}</div>}</section><section className="rounded-2xl border border-white/[0.08] bg-white/[0.035] p-6"><h2 className="text-lg font-semibold text-white">Activity timeline</h2><p className="mt-4 text-sm text-slate-500">Run activity will appear here as persisted SSE stage transitions arrive.</p></section></div></AppShell>
}
