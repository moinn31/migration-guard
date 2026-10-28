'use client'
import { useParams } from 'next/navigation'
import { RunShell } from '@/components/run-shell'
import { LoadingState } from '@/components/app-shell'
import { useRunDetails } from '@/lib/api/hooks'
export default function BuildPage() { const { id } = useParams<{ id: string }>(); const query = useRunDetails(id); return <RunShell title="Build and test"><div className="grid gap-6 p-6 lg:grid-cols-2 lg:p-10">{query.isLoading ? <LoadingState /> : [['Baseline · Java 8', 'Original immutable snapshot'], ['Migrated · Java 17', 'Working copy after migration']].map(([title, subtitle]) => <section key={title} className="rounded-2xl border border-white/[0.08] bg-white/[0.035] p-6"><h2 className="font-semibold text-white">{title}</h2><p className="mt-1 text-xs text-slate-500">{subtitle}</p><div className="mt-6 rounded-xl bg-black/20 p-5 text-sm text-slate-500">Build evidence is persisted when Docker execution is enabled.</div><pre className="mt-4 max-h-64 overflow-auto text-xs text-slate-500">No log excerpt available.</pre></section>)}</div></RunShell> }
