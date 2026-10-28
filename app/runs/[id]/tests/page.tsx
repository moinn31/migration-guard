'use client'
import { useParams } from 'next/navigation'
import { RunShell } from '@/components/run-shell'
import { LoadingState } from '@/components/app-shell'
import { useRunDetails } from '@/lib/api/hooks'
export default function TestsPage() { const { id } = useParams<{ id: string }>(); const query = useRunDetails(id); return <RunShell title="Test integrity"><div className="p-6 lg:p-10">{query.isLoading ? <LoadingState /> : <section className="rounded-2xl border border-white/[0.08] bg-white/[0.035] p-6"><h2 className="font-semibold text-white">Baseline vs migrated matrix</h2><p className="mt-2 text-sm text-slate-500">Each result is compared against persisted baseline evidence. Missing results require review.</p><div className="mt-6 grid grid-cols-3 gap-3 text-xs text-slate-400"><span>Test</span><span>Baseline</span><span>Migrated</span><div className="col-span-3 rounded-xl border border-dashed border-white/10 p-8 text-center text-slate-500">No test results are available for this run yet.</div></div></section>}</div></RunShell> }
