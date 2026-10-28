'use client'

import { useParams } from 'next/navigation'
import { RunShell } from '@/components/run-shell'
import { ErrorState, LoadingState } from '@/components/app-shell'
import { useRun, useRunEvents } from '@/lib/api/hooks'

export default function RunPage() {
  const { id } = useParams<{ id: string }>()
  const run = useRun(id)
  const stream = useRunEvents(id)
  if (run.isLoading) return <RunShell title="Run overview"><div className="p-10"><LoadingState /></div></RunShell>
  if (run.error || !run.data) return <RunShell title="Run overview"><div className="p-10"><ErrorState message={run.error?.message} /></div></RunShell>
  const stages = (stream.event?.stages ?? []) as Array<{ name: string; status: string; evidence_reference?: string }>
  return <RunShell title="Live pipeline"><div className="grid gap-6 p-6 lg:grid-cols-[1fr_360px] lg:p-10"><section className="rounded-2xl border border-white/[0.08] bg-white/[0.035] p-6"><div className="flex items-center justify-between"><h2 className="text-lg font-semibold text-white">Pipeline stages</h2><span className="text-xs text-slate-500">{stream.connected ? 'Live SSE connected' : 'Reconnecting…'}</span></div><div className="mt-6 space-y-3">{(stages.length ? stages : [{ name: run.data.state, status: 'RUNNING' }]).map((stage) => <div key={stage.name} className="flex items-center justify-between rounded-xl border border-white/[0.06] p-4"><div><p className="font-medium text-white">{stage.name.replaceAll('_', ' ')}</p><p className="mt-1 text-xs text-slate-500">{stage.evidence_reference || 'Waiting for evidence'}</p></div><span className="rounded-full bg-white/10 px-2 py-1 text-[10px] text-slate-300">{stage.status}</span></div>)}</div></section><section className="rounded-2xl border border-white/[0.08] bg-black/20 p-5"><h2 className="font-semibold text-white">Streaming logs</h2><pre className="mt-4 max-h-96 overflow-auto whitespace-pre-wrap text-xs text-slate-500">Stage transitions and build excerpts appear here as evidence is persisted.</pre></section></div></RunShell>
}
