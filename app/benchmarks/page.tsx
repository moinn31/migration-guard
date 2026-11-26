'use client'
import { AppShell, LoadingState, PageHeader } from '@/components/app-shell'
import { api } from '@/lib/api/client'
import { useQuery } from '@tanstack/react-query'

type Evidence = { status?: string; limitations?: string; items?: Array<{ run_id: string; build_success: boolean | null; tests_preserved: boolean | null }>; metrics?: Record<string, number | null> }
export default function BenchmarksPage() {
  const query = useQuery({ queryKey: ['benchmarks'], queryFn: async () => { const { data, error } = await api.GET('/benchmarks'); if (error) throw new Error('Unable to load verification metrics'); return data as Evidence } })
  const observed = (value: boolean | null) => value === null ? 'Unavailable' : value ? 'Passed' : 'Failed'
  return <AppShell><PageHeader eyebrow="Evaluation" title="Verification evidence" /><div className="p-6 lg:p-10">{query.isLoading ? <LoadingState /> : query.isError ? <p role="alert" className="text-red-300">{query.error.message}</p> : <section className="rounded-2xl border border-white/10 p-8 text-slate-300">
    <h2 className="font-semibold text-white">Observed verification runs</h2>
    <p className="mt-2 text-sm">{query.data?.items?.length ? query.data.limitations : 'No persisted verification reports are available yet.'}</p>
    <div className="mt-4 grid gap-3 sm:grid-cols-2">{Object.entries(query.data?.metrics ?? {}).map(([name, value]) => <p key={name} className="text-sm">{name.replaceAll('_', ' ')}: <strong>{value === null ? 'Unavailable' : `${(value * 100).toFixed(1)}%`}</strong></p>)}</div>
    {!!query.data?.items?.length && <table className="mt-6 w-full text-left text-sm"><thead><tr><th>Run</th><th>Builds</th><th>Tests preserved</th></tr></thead><tbody>{query.data.items.map(item => <tr key={item.run_id}><td className="py-2"><a className="text-cyan-300" href={`/runs/${item.run_id}/report`}>{item.run_id}</a></td><td>{observed(item.build_success)}</td><td>{observed(item.tests_preserved)}</td></tr>)}</tbody></table>}
  </section>}</div></AppShell>
}
