'use client'

import Link from 'next/link'
import { useParams } from 'next/navigation'
import { AppShell, PageHeader } from './app-shell'

export function RunShell({ children, title }: { children: React.ReactNode; title: string }) {
  const { id } = useParams<{ id: string }>()
  const links = [['Overview', `/runs/${id}`], ['Analysis', `/runs/${id}/analysis`], ['Changes', `/runs/${id}/changes`], ['Tests', `/runs/${id}/tests`], ['Build', `/runs/${id}/build`], ['Verdict', `/runs/${id}/verdict`], ['Report', `/runs/${id}/report`]]
  return <AppShell><PageHeader eyebrow={`Run ${id.slice(0, 8)}`} title={title} /><div className="border-b border-white/[0.08] px-6 lg:px-10"><nav className="flex gap-5 overflow-x-auto" aria-label="Run navigation">{links.map(([label, href]) => <Link key={href} href={href} className="whitespace-nowrap border-b-2 border-transparent py-3 text-xs text-slate-400 hover:border-cyan-300 hover:text-white">{label}</Link>)}</nav></div>{children}</AppShell>
}
