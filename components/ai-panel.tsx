'use client'

import { useState } from 'react'
import { useAiAction } from '@/lib/api/hooks'

export function AiPanel({ runId }: { runId: string }) {
  const [action, setAction] = useState<'explain' | 'suggest-fix' | 'summary'>('explain')
  const mutation = useAiAction(runId, action)
  const output = mutation.data ? JSON.stringify(mutation.data, null, 2) : null
  const error = mutation.error instanceof Error ? mutation.error.message : 'AI assistance failed.'
  return (
    <aside className="rounded-2xl border border-violet-300/20 bg-violet-300/5 p-5">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-white">AI assistance</h2>
        <span className="text-[10px] uppercase tracking-wide text-violet-200">AI-generated – unverified</span>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {(['explain', 'suggest-fix', 'summary'] as const).map((value) => (
          <button key={value} onClick={() => { setAction(value); mutation.reset() }} className={`rounded-lg px-2.5 py-1.5 text-xs ${action === value ? 'bg-violet-300/20 text-violet-100' : 'text-slate-400 hover:text-white'}`}>{value.replace('-', ' ')}</button>
        ))}
      </div>
      <button onClick={() => mutation.mutate()} disabled={mutation.isPending} className="mt-4 rounded-lg bg-violet-300 px-3 py-2 text-xs font-semibold text-slate-950 disabled:opacity-40">{mutation.isPending ? 'Thinking…' : 'Run assistance'}</button>
      {output && <pre className="mt-4 max-h-48 overflow-auto whitespace-pre-wrap text-xs text-slate-300">{output}</pre>}
      {mutation.error && <p className="mt-3 text-xs text-red-300">{error}</p>}
    </aside>
  )
}
