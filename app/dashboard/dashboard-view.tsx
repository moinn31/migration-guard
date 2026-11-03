'use client'

import Link from 'next/link'
import { Plus, ShieldAlert, ShieldCheck, Timer, Workflow, ArrowRight, FolderGit2 } from 'lucide-react'
import { AppShell, PageHeader } from '@/components/app-shell'
import { useProjects } from '@/lib/api/hooks'

export default function DashboardPage() {
  const projects = useProjects()
  const headerAction = (
    <Link
      href="/projects/new"
      className="inline-flex items-center gap-2 rounded-xl bg-cyan-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 shadow-sm"
    >
      <Plus className="size-4" />
      New project
    </Link>
  )

  const items = projects.data ?? []
  const cards: Array<[string, number, typeof Workflow]> = [
    ['Projects', items.length, Workflow],
    ['Verified', items.length > 0 ? items.length : 0, ShieldCheck],
    ['Needs review', 0, ShieldAlert],
    ['Active runs', 0, Timer],
  ]

  return (
    <AppShell>
      <PageHeader eyebrow="Verification workspace" title="Dashboard" action={headerAction} />
      <div className="space-y-8 p-6 lg:p-10">
        <div className="grid gap-4 md:grid-cols-4">
          {cards.map(([label, value, Icon]) => (
            <div key={label} className="rounded-2xl border border-white/[0.08] bg-white/[0.035] p-5 shadow-sm">
              <Icon className="size-5 text-cyan-400" />
              <p className="mt-6 text-sm text-slate-400">{label}</p>
              <p className="mt-1 text-3xl font-semibold text-white">{value}</p>
            </div>
          ))}
        </div>

        {projects.error && (
          <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-300">
            Unable to load projects from the database. Ensure the backend server is active.
          </div>
        )}

        <section className="rounded-2xl border border-white/[0.08] bg-white/[0.035] p-6 shadow-sm">
          <div className="flex items-center justify-between pb-4 border-b border-white/[0.06]">
            <div>
              <h2 className="text-lg font-semibold text-white">Recent projects</h2>
              <p className="text-xs text-slate-400 mt-0.5">Cloned repositories and source files stored in Neon PostgreSQL</p>
            </div>
            {items.length > 0 && (
              <span className="rounded-full bg-cyan-950/60 border border-cyan-500/30 px-3 py-1 text-xs font-mono text-cyan-300">
                {items.length} {items.length === 1 ? 'project' : 'projects'} saved
              </span>
            )}
          </div>

          {projects.isLoading ? (
            <div className="py-12 text-center text-sm text-slate-400 flex items-center justify-center gap-2">
              <div className="size-4 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent" />
              Loading your saved projects from database...
            </div>
          ) : items.length === 0 ? (
            <div className="py-14 text-center">
              <FolderGit2 className="size-10 text-slate-600 mx-auto mb-3" />
              <p className="text-sm font-medium text-slate-300">No projects yet</p>
              <p className="text-xs text-slate-500 mt-1">Import a GitHub repository to clone files and start verification.</p>
              <Link
                href="/projects/new"
                className="inline-flex items-center gap-1.5 mt-4 rounded-lg bg-white/10 hover:bg-white/15 px-3 py-1.5 text-xs font-semibold text-white transition"
              >
                <Plus className="size-3.5" />
                Import your first project
              </Link>
            </div>
          ) : (
            <div className="mt-5 grid gap-3">
              {items.map((project) => (
                <Link
                  key={project.id}
                  href={`/workspace/${project.id}`}
                  className="group flex items-center justify-between rounded-xl border border-white/[0.06] bg-white/[0.015] p-4 transition hover:border-cyan-500/40 hover:bg-white/[0.04]"
                >
                  <div className="flex items-center gap-3.5">
                    <div className="size-9 rounded-lg border border-white/10 bg-white/5 flex items-center justify-center group-hover:border-cyan-500/30 group-hover:bg-cyan-950/30">
                      <FolderGit2 className="size-4 text-slate-400 group-hover:text-cyan-300 transition-colors" />
                    </div>
                    <div>
                      <p className="font-medium text-white group-hover:text-cyan-200 transition-colors">{project.name}</p>
                      <p className="mt-0.5 text-xs text-slate-400 font-mono">
                        {project.repository_url || 'Repository'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-cyan-400 group-hover:text-cyan-300 transition-colors">
                      Open Workspace
                      <ArrowRight className="size-3.5 group-hover:translate-x-0.5 transition-transform" />
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-2xl border border-white/[0.08] bg-white/[0.035] p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-white">Activity timeline</h2>
          <p className="mt-3 text-sm text-slate-400">Run activity will appear here as persisted SSE stage transitions arrive.</p>
        </section>
      </div>
    </AppShell>
  )
}
