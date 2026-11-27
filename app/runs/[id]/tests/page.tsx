'use client'
import { useParams } from 'next/navigation'
import { RunShell } from '@/components/run-shell'
import { LoadingState } from '@/components/app-shell'
import { useReport, useRun } from '@/lib/api/hooks'

type Test = { name: string; status: string }
type Coverage = { measured?: boolean; counters?: Record<string, { ratio: number | null }> }
type Evidence = { tests?: { baseline: Test[]; migrated: Test[] }; coverage?: { baseline: Coverage | null; migrated: Coverage | null }; verdict?: { value: string; reasons: Array<{ rule_id: string; message: string }> } }
export default function TestsPage() {
  const { id } = useParams<{ id: string }>()
  const run = useRun(id)
  const query = useReport(id)
  const report = query.data?.content as Evidence | undefined
  const before = new Map(report?.tests?.baseline.map(test => [test.name, test.status]) ?? [])
  const after = new Map(report?.tests?.migrated.map(test => [test.name, test.status]) ?? [])
  const names = [...new Set([...before.keys(), ...after.keys()])].sort()
  const percent = (coverage: Coverage | null | undefined, metric: string) => {
    const ratio = coverage?.counters?.[metric]?.ratio
    return coverage?.measured && ratio != null ? `${(ratio * 100).toFixed(1)}%` : 'Unavailable'
  }
  return <RunShell title="Tests and coverage"><div className="space-y-6 p-6 lg:p-10">
    <p className="text-sm text-slate-300">Run status: {run.data?.state ?? 'Loading...'} {report?.verdict && ` / ${report.verdict.value}`}</p>
    {query.isLoading ? <LoadingState /> : !report ? <p className="text-sm text-slate-400">The verification report is not available yet. This page refreshes while the worker runs. {run.error?.message}</p> : <>
      <section className="rounded-2xl border border-white/10 p-6"><h2 className="font-semibold text-white">Baseline vs migrated tests</h2><div className="mt-4 overflow-auto"><table className="w-full text-left text-xs text-slate-300"><thead><tr><th className="p-2">Test</th><th className="p-2">Baseline Java 8</th><th className="p-2">Migrated Java 17</th></tr></thead><tbody>{names.map(name => <tr key={name} className="border-t border-white/10"><td className="p-2 font-mono">{name}</td><td className="p-2">{before.get(name) ?? 'Missing'}</td><td className="p-2">{after.get(name) ?? 'Missing'}</td></tr>)}</tbody></table></div>{!names.length && <p className="mt-4 text-sm text-slate-400">No test results were recorded. Review the build evidence.</p>}</section>
      <section className="rounded-2xl border border-white/10 p-6"><h2 className="font-semibold text-white">Measured JaCoCo coverage</h2><table className="mt-4 w-full text-left text-sm text-slate-300"><thead><tr><th className="p-2">Metric</th><th className="p-2">Baseline</th><th className="p-2">Migrated</th></tr></thead><tbody>{['line', 'branch', 'instruction'].map(metric => <tr key={metric}><td className="p-2 capitalize">{metric}</td><td className="p-2">{percent(report.coverage?.baseline, metric)}</td><td className="p-2">{percent(report.coverage?.migrated, metric)}</td></tr>)}</tbody></table><p className="mt-4 text-xs text-slate-400">Unavailable evidence is never counted as 100%. Passing checks do not prove behavioral equivalence.</p></section>
      <section className="rounded-2xl border border-white/10 p-6"><h2 className="font-semibold text-white">Review findings</h2><ul className="mt-4 space-y-2 text-sm text-slate-300">{report.verdict?.reasons.map((reason, index) => <li key={`${reason.rule_id}-${index}`}>{reason.message}</li>)}</ul></section>
    </>}
  </div></RunShell>
}
