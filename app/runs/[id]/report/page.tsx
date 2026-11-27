'use client'
import { useState } from 'react'
import { useParams } from 'next/navigation'
import { RunShell } from '@/components/run-shell'
import { LoadingState } from '@/components/app-shell'
import { useReport } from '@/lib/api/hooks'
import { authenticatedFetch } from '@/lib/api/client'
export default function ReportPage() {
  const { id } = useParams<{ id: string }>()
  const query = useReport(id)
  const [error, setError] = useState('')
  async function download(format: string) {
    setError('')
    try {
      const suffix = format === 'json' ? '' : `.${format}`
      const response = await authenticatedFetch(`${process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000'}/runs/${id}/report${suffix}`)
      if (!response.ok) throw new Error('Unable to download report. Retry after verification finishes.')
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = `verification-${id}.${format}`
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (error) { setError(error instanceof Error ? error.message : 'Report download failed') }
  }
  return <RunShell title="Evidence report"><div className="p-6 lg:p-10">{query.isLoading ? <LoadingState /> : <section className="rounded-2xl border border-white/10 p-6"><div className="flex flex-wrap gap-3">{['json', 'md', 'html', 'pdf'].map(format => <button key={format} className="rounded-xl border border-white/10 px-3 py-2 text-xs text-slate-300" onClick={() => download(format)}>{format.toUpperCase()}</button>)}</div>{error && <p role="alert" className="mt-3 text-sm text-red-300">{error}</p>}<pre className="mt-6 max-h-[70vh] overflow-auto rounded-xl bg-black/30 p-5 text-xs leading-6 text-slate-400">{JSON.stringify(query.data?.content ?? {}, null, 2)}</pre></section>}</div></RunShell>
}
