'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Suspense, useEffect, useState } from 'react'
import { BarChart3, FolderKanban, Search, Settings, ShieldCheck, Sun, ExternalLink } from 'lucide-react'
import { Show, SignInButton, SignUpButton, UserButton } from '@clerk/nextjs'
import { cn } from '@/lib/utils'

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [palette, setPalette] = useState(false)
  const [light, setLight] = useState(false)

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setPalette(true)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const links = [
    { href: '/dashboard', label: 'Dashboard', icon: BarChart3 },
    { href: '/settings', label: 'Settings', icon: Settings },
    { href: '/benchmarks', label: 'Benchmarks', icon: FolderKanban },
  ]

  return (
    <div className={cn('min-h-screen text-slate-100', light ? 'bg-slate-100 text-slate-950' : 'bg-[#080a0f]')}>
      {/* Sidebar */}
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-white/[0.08] bg-black/20 p-5 lg:flex lg:flex-col lg:justify-between">
        <div>
          <Link href="/dashboard" className="flex items-center gap-3">
            <span className="flex size-9 items-center justify-center rounded-xl bg-cyan-300 text-slate-950 shadow-lg shadow-cyan-300/10">
              <ShieldCheck className="size-5" />
            </span>
            <span className="font-semibold text-white">
              Migration<span className="text-cyan-300">Guard</span>
            </span>
          </Link>

          <nav className="mt-10 space-y-1.5" aria-label="Primary navigation">
            {links.map(({ href, label, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                className={cn(
                  'flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition-colors',
                  pathname === href
                    ? 'bg-cyan-300/10 text-cyan-200'
                    : 'text-slate-400 hover:bg-white/[0.05] hover:text-white'
                )}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            ))}
          </nav>
        </div>

        {/* Sidebar Footer */}
        <div className="border-t border-white/[0.08] pt-4">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span className="flex items-center gap-1.5">
              <span className="size-2 rounded-full bg-emerald-400 animate-pulse" />
              Connected
            </span>
            <span className="font-mono text-[10px] text-slate-600">v0.1.0</span>
          </div>
        </div>
      </aside>

      {/* Main Area with Top Header */}
      <div className="lg:pl-64">
        {/* Top Navbar Header (Google / YouTube style) */}
        <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-white/[0.08] bg-[#080a0f]/80 px-6 backdrop-blur-md lg:px-10">
          {/* Quick Search */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => setPalette(true)}
              className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3.5 py-1.5 text-xs text-slate-400 transition-colors hover:border-white/20 hover:text-white"
            >
              <Search className="size-3.5 text-slate-500" />
              <span className="hidden sm:inline">Search workspace…</span>
              <kbd className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-slate-400">⌘K</kbd>
            </button>
          </div>

          {/* Top Right: Account Information & Actions */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => setLight((v) => !v)}
              className="flex size-9 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.03] text-slate-400 transition-colors hover:border-white/20 hover:text-white"
              aria-label="Toggle theme"
            >
              <Sun className="size-4" />
            </button>

            <div className="h-4 w-px bg-white/10" />

            <Suspense fallback={<div className="size-8 animate-pulse rounded-full bg-white/10" />}>
              <Show when="signed-in">
                <div className="flex items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.03] p-1 pr-3 hover:border-white/20 transition-colors">
                  <UserButton
                    showName
                    appearance={{
                      elements: {
                        userButtonBox: 'flex-row-reverse gap-2',
                        userButtonOuterIdentifier: 'text-xs font-medium text-slate-200',
                        avatarBox: 'size-7 border border-white/10',
                      },
                    }}
                  />
                </div>
              </Show>
              <Show when="signed-out">
                <div className="flex items-center gap-2">
                  <SignInButton mode="modal">
                    <button className="rounded-xl bg-cyan-300 px-3.5 py-1.5 text-xs font-semibold text-slate-950 transition-colors hover:bg-cyan-200">
                      Sign in
                    </button>
                  </SignInButton>
                  <SignUpButton mode="modal">
                    <button className="rounded-xl border border-white/10 px-3.5 py-1.5 text-xs font-semibold text-slate-300 transition-colors hover:bg-white/[0.05]">
                      Sign up
                    </button>
                  </SignUpButton>
                </div>
              </Show>
            </Suspense>
          </div>
        </header>

        {/* Page Content */}
        <main>{children}</main>
      </div>

      {/* Command Palette */}
      {palette && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-10 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          onClick={() => setPalette(false)}
        >
          <div
            className="w-full max-w-lg rounded-2xl border border-white/10 bg-[#11151d] p-4 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center gap-2 border-b border-white/10 pb-3">
              <Search className="size-4 text-slate-500" />
              <input
                autoFocus
                placeholder="Search workspace…"
                className="flex-1 bg-transparent text-sm text-white outline-none"
                onKeyDown={(event) => event.key === 'Escape' && setPalette(false)}
              />
            </div>
            <p className="p-4 text-xs text-slate-500">
              Use the navigation to open projects, runs, settings, and benchmarks.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

export function PageHeader({ eyebrow, title, action }: { eyebrow: string; title: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col justify-between gap-4 border-b border-white/[0.08] px-6 py-7 sm:flex-row sm:items-end lg:px-10">
      <div>
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-cyan-300">{eyebrow}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">{title}</h1>
      </div>
      {action}
    </div>
  )
}

export function LoadingState() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="h-5 w-48 rounded bg-white/10" />
      <div className="h-24 rounded-2xl bg-white/5" />
      <div className="h-24 rounded-2xl bg-white/5" />
    </div>
  )
}

export function ErrorState({ message = 'Unable to load this evidence.' }: { message?: string }) {
  return <div className="rounded-2xl border border-red-300/20 bg-red-300/10 p-5 text-sm text-red-200">{message}</div>
}
