'use client'
import { AppShell, LoadingState, PageHeader } from '@/components/app-shell'
import { api } from '@/lib/api/client'
import { useQuery } from '@tanstack/react-query'
export default function BenchmarksPage() {
  const query = useQuery({ queryKey: ['benchmarks'], queryFn: async () => { const { data, error } = await api.GET('/benchmarks'); if (error) throw new Error('Unable to load benchmark results'); return data as { status?: string } } })
  return <AppShell><PageHeader eyebrow="Evaluation" title="Benchmarks" /><div className="p-6 lg:p-10">{query.isLoading ? <LoadingState /> : <section className="rounded-2xl border border-white/[0.08] bg-white/[0.035] p-8"><h2 className="font-semibold text-white">MigrationBench and Mutation Lab</h2><p className="mt-2 text-sm text-slate-500">{query.data?.status === 'evaluation_not_run' ? 'No evaluation run has produced persisted results yet.' : 'Evaluation results are available.'}</p></section>}</div></AppShell>
}
