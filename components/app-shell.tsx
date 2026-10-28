'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import { BarChart3, FolderKanban, LogOut, Search, Settings, ShieldCheck, Sun } from 'lucide-react'
import { clearToken } from '@/lib/api/client'
import { cn } from '@/lib/utils'

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [palette, setPalette] = useState(false)
  const [light, setLight] = useState(false)
  useEffect(() => {
    const handler = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setPalette(true) } }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])
  const links = [
    { href: '/dashboard', label: 'Dashboard', icon: BarChart3 },
    { href: '/settings', label: 'Settings', icon: Settings },
    { href: '/benchmarks', label: 'Benchmarks', icon: FolderKanban },
  ]
  return <div className={cn('min-h-screen text-slate-100', light ? 'bg-slate-100 text-slate-950' : 'bg-[#080a0f')}>
    <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-white/[0.08] bg-black/20 p-5 lg:block">
      <Link href="/dashboard" className="flex items-center gap-3"><span className="flex size-9 items-center justify-center rounded-xl bg-cyan-300 text-slate-950"><ShieldCheck className="size-5" /></span><span className="font-semibold text-white">Migration<span className="text-cyan-300">Guard</span></span></Link>
      <nav className="mt-10 space-y-2" aria-label="Primary navigation">{links.map(({ href, label, icon: Icon }) => <Link key={href} href={href} className={cn('flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm', pathname === href ? 'bg-cyan-300/10 text-cyan-200' : 'text-slate-400 hover:bg-white/[0.05] hover:text-white')}><Icon className="size-4" />{label}</Link>)}</nav>
      <div className="absolute bottom-5 left-5 flex gap-3"><button onClick={() => setLight((value) => !value)} className="flex items-center gap-2 text-sm text-slate-500 hover:text-white" aria-label="Toggle theme"><Sun className="size-4" /></button><button onClick={() => { clearToken(); window.location.href = '/' }} className="flex items-center gap-3 text-sm text-slate-500 hover:text-white"><LogOut className="size-4" />Sign out</button></div>
    </aside>
    <main className="lg:pl-64">{children}</main>{palette && <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-10" role="dialog" aria-modal="true" onClick={() => setPalette(false)}><div className="w-full max-w-lg rounded-2xl border border-white/10 bg-[#11151d] p-4 shadow-2xl" onClick={(event) => event.stopPropagation()}><div className="flex items-center gap-2 border-b border-white/10 pb-3"><Search className="size-4 text-slate-500" /><input autoFocus placeholder="Search workspace…" className="flex-1 bg-transparent text-sm text-white outline-none" onKeyDown={(event) => event.key === 'Escape' && setPalette(false)} /></div><p className="p-4 text-xs text-slate-500">Use the navigation to open projects, runs, settings, and benchmarks.</p></div></div>}
  </div>
}

export function PageHeader({ eyebrow, title, action }: { eyebrow: string; title: string; action?: React.ReactNode }) {
  return <header className="flex flex-col justify-between gap-4 border-b border-white/[0.08] px-6 py-7 sm:flex-row sm:items-end lg:px-10"><div><p className="font-mono text-[10px] uppercase tracking-[0.2em] text-cyan-300">{eyebrow}</p><h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">{title}</h1></div>{action}</header>
}

export function LoadingState() {
  return <div className="animate-pulse space-y-3"><div className="h-5 w-48 rounded bg-white/10" /><div className="h-24 rounded-2xl bg-white/5" /><div className="h-24 rounded-2xl bg-white/5" /></div>
}

export function ErrorState({ message = 'Unable to load this evidence.' }: { message?: string }) {
  return <div className="rounded-2xl border border-red-300/20 bg-red-300/10 p-5 text-sm text-red-200">{message}</div>
}
