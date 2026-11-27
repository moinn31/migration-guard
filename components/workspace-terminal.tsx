'use client'

import React, { useState, useEffect, useRef, useMemo } from 'react'
import {
  Terminal as TerminalIcon,
  Plus,
  X,
  Trash2,
  Square,
  ChevronDown,
  ChevronUp,
  Maximize2,
  Minimize2,
  Play,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Sparkles,
  Info,
  ArrowDownCircle,
} from 'lucide-react'

export interface TerminalJob {
  id: string
  terminal_id?: string
  command: string
  status: string
  output: string
  cwd?: string
  exit_code?: number | null
  process_running?: boolean
  notices?: Array<{ id: string; text: string }>
}

interface TerminalTab {
  id: string
  title: string
  type: 'user' | 'ai'
}

interface WorkspaceTerminalProps {
  projectId: string
  terminalEnabled: boolean
  workspaceRequest: (path: string, options?: RequestInit) => Promise<any>
  onErrorCaptured?: (errorInfo: { id: string; command: string; output: string; exit_code?: number | null; sentry_event_id?: string }) => void
}

function formatCwd(rawCwd?: string): string {
  if (!rawCwd) return '~/repo'
  const normalized = rawCwd.replace(/\\/g, '/')
  const projectsIndex = normalized.indexOf('/workspace/projects/')
  if (projectsIndex !== -1) {
    const afterProjects = normalized.substring(projectsIndex + '/workspace/projects/'.length)
    const firstSlash = afterProjects.indexOf('/')
    if (firstSlash === -1) {
      return '~/repo'
    }
    return `~/repo${afterProjects.substring(firstSlash)}`
  }
  const repoIndex = normalized.indexOf('/workspace/repository')
  if (repoIndex !== -1) {
    const sub = normalized.substring(repoIndex + '/workspace/repository'.length)
    return sub ? `~/repo${sub}` : '~/repo'
  }
  return normalized || '~/repo'
}

export function WorkspaceTerminal({
  projectId,
  terminalEnabled,
  workspaceRequest,
  onErrorCaptured,
}: WorkspaceTerminalProps) {
  // Tabs State
  const [tabs, setTabs] = useState<TerminalTab[]>([
    { id: 'term-1', title: 'Terminal 1', type: 'user' },
  ])
  const [activeTabId, setActiveTabId] = useState<string>('term-1')
  const [isMinimized, setIsMinimized] = useState<boolean>(false)
  const [isExpanded, setIsExpanded] = useState<boolean>(false)

  // Command input & history
  const [commandInput, setCommandInput] = useState<string>('')
  const [commandHistory, setCommandHistory] = useState<string[]>([])
  const [historyIndex, setHistoryIndex] = useState<number>(-1)

  // Permanent cleared jobs per tab (so old jobs NEVER reappear on background poll)
  const [clearedJobIdsByTab, setClearedJobIdsByTab] = useState<Record<string, string[]>>({})

  // Jobs & execution state
  const [jobs, setJobs] = useState<TerminalJob[]>([])
  const [runningJobId, setRunningJobId] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string>('')

  // Smart scrolling state: don't kick user down if they scrolled up to read past logs
  const consoleContainerRef = useRef<HTMLDivElement | null>(null)
  const isAutoScrollActiveRef = useRef<boolean>(true)
  const [showScrollBottomBtn, setShowScrollBottomBtn] = useState<boolean>(false)
  const inputRef = useRef<HTMLInputElement | null>(null)

  // Determine current working directory & filtered jobs for active tab
  const activeTabJobs = useMemo(() => {
    const clearedSet = new Set(clearedJobIdsByTab[activeTabId] || [])
    return jobs.filter((j) => {
      const matchesTab =
        j.terminal_id === activeTabId || (!j.terminal_id && activeTabId === 'term-1')
      return matchesTab && !clearedSet.has(j.id)
    })
  }, [jobs, activeTabId, clearedJobIdsByTab])

  const currentCwd = useMemo(() => {
    const lastWithCwd = [...activeTabJobs].reverse().find((j) => j.cwd)
    return lastWithCwd?.cwd || '/workspace/repository'
  }, [activeTabJobs])

  const displayPromptDir = useMemo(() => formatCwd(currentCwd), [currentCwd])

  // Scroll helper
  const scrollToBottom = (behavior: ScrollBehavior = 'smooth') => {
    const el = consoleContainerRef.current
    if (el) {
      el.scrollTo({
        top: el.scrollHeight,
        behavior,
      })
    }
  }

  // Handle user scroll event: if scrolled away from bottom, disable auto-scroll
  const handleScroll = () => {
    const el = consoleContainerRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    const isNearBottom = distanceFromBottom < 60
    isAutoScrollActiveRef.current = isNearBottom
    setShowScrollBottomBtn(!isNearBottom)
  }

  // Reset tabs, jobs, and state whenever projectId changes
  useEffect(() => {
    setTabs([{ id: 'term-1', title: 'Terminal 1', type: 'user' }])
    setActiveTabId('term-1')
    setJobs([])
    setClearedJobIdsByTab({})
    setCommandHistory([])
    setHistoryIndex(-1)
    setRunningJobId(null)
    setErrorMsg('')
  }, [projectId])

  // Adaptive polling: fast (250ms) while running, idle (2500ms) otherwise
  useEffect(() => {
    if (!terminalEnabled) return
    let active = true

    const fetchJobs = async () => {
      try {
        const data: TerminalJob[] = await workspaceRequest('/terminal/jobs')
        if (!active) return

        setJobs((prev) => {
          // Merge preserving any optimistic local additions
          const ids = new Set(data.map((d) => d.id))
          const remainingOptimistic = prev.filter(
            (p) => p.id.startsWith('temp-') && !ids.has(p.id)
          )
          return [...data, ...remainingOptimistic]
        })

        // Detect AI jobs and auto-create tab (e.g. "AI Terminal", "AI Terminal 2")
        data.forEach((job) => {
          const tid = job.terminal_id || 'term-1'
          if (tid === 'ai-terminal' || tid.startsWith('ai-') || tid.includes('ai')) {
            setTabs((prev) => {
              if (prev.some((t) => t.id === tid)) return prev
              const title =
                tid === 'ai-terminal'
                  ? 'AI Terminal'
                  : `AI Terminal ${tid.replace('ai-terminal-', '').replace(/[^0-9]/g, '') || '2'}`
              return [
                ...prev,
                { id: tid, title, type: 'ai' },
              ]
            })

            // Copilot-style auto-switch to active AI terminal when AI job starts
            if (job.status === 'running') {
              setActiveTabId((current) => {
                if (current.startsWith('term-')) {
                  return tid
                }
                return current
              })
            }
          }

          // Check if job failed and report to Left Communication Panel
          const isError =
            job.status === 'failed' ||
            (job.exit_code != null && job.exit_code !== 0) ||
            Boolean((job as any).sentry_event_id)
          if (isError && onErrorCaptured) {
            onErrorCaptured({
              id: job.id,
              command: job.command,
              output: job.output,
              exit_code: job.exit_code,
              sentry_event_id: (job as any).sentry_event_id,
            })
          }
        })

        // Check if any job in active tab is still running
        const activeRunning = data.find(
          (j) =>
            (j.terminal_id === activeTabId || (!j.terminal_id && activeTabId === 'term-1')) &&
            (j.status === 'running' || j.status === 'queued')
        )
        setRunningJobId(activeRunning ? activeRunning.id : null)
        setErrorMsg('')
      } catch (err) {
        if (active) {
          setErrorMsg(err instanceof Error ? err.message : 'Unable to poll terminal')
        }
      }
    }

    fetchJobs()
    const pollInterval = runningJobId ? 250 : 2500
    const interval = setInterval(fetchJobs, pollInterval)
    return () => {
      active = false
      clearInterval(interval)
    }
  }, [projectId, terminalEnabled, activeTabId, runningJobId])

  // Scroll to bottom on job updates ONLY if user has not scrolled up to read past logs
  useEffect(() => {
    if (!isMinimized && isAutoScrollActiveRef.current) {
      scrollToBottom('smooth')
    }
  }, [activeTabJobs, isMinimized])

  // Add new tab
  const handleAddTab = () => {
    const userTabs = tabs.filter((t) => t.type === 'user')
    const nextNum = userTabs.length + 1
    const newId = `term-${Date.now()}`
    const newTab: TerminalTab = {
      id: newId,
      title: `Terminal ${nextNum}`,
      type: 'user',
    }
    setTabs((prev) => [...prev, newTab])
    setActiveTabId(newId)
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  // Close tab: also permanently purge its commands from database/Azure
  const handleCloseTab = async (idToClose: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (tabs.length <= 1) return
    const nextTabs = tabs.filter((t) => t.id !== idToClose)
    setTabs(nextTabs)
    if (activeTabId === idToClose) {
      setActiveTabId(nextTabs[nextTabs.length - 1].id)
    }
    try {
      await workspaceRequest(`/terminal/clear?terminal_id=${encodeURIComponent(idToClose)}`, {
        method: 'DELETE',
      })
    } catch (err) {
      console.warn('Failed to clear terminal on server:', err)
    }
    setJobs((prev) => prev.filter((j) => j.terminal_id !== idToClose))
  }

  // Clear active terminal: guarantees old logs NEVER reappear on background poll and purges on server
  const handleClear = async () => {
    const idsToClear = jobs
      .filter(
        (j) =>
          (j.terminal_id === activeTabId || (!j.terminal_id && activeTabId === 'term-1')) &&
          j.status !== 'running'
      )
      .map((j) => j.id)

    setClearedJobIdsByTab((prev) => ({
      ...prev,
      [activeTabId]: Array.from(new Set([...(prev[activeTabId] || []), ...idsToClear])),
    }))

    setJobs((prev) => prev.filter((j) => !idsToClear.includes(j.id)))
    setShowScrollBottomBtn(false)
    isAutoScrollActiveRef.current = true

    try {
      await workspaceRequest(`/terminal/clear?terminal_id=${encodeURIComponent(activeTabId)}`, {
        method: 'DELETE',
      })
    } catch (err) {
      console.warn('Failed to clear terminal on server:', err)
    }
  }

  // Execute command
  const handleRunCommand = async (e?: React.FormEvent) => {
    if (e) e.preventDefault()
    const trimmed = commandInput.trim()
    if (!trimmed || !terminalEnabled) return

    // 1. Built-in CMD clear support (cls or clear)
    if (trimmed.toLowerCase() === 'cls' || trimmed.toLowerCase() === 'clear') {
      handleClear()
      setCommandHistory((prev) => [...prev, trimmed])
      setHistoryIndex(-1)
      setCommandInput('')
      return
    }

    // 2. Re-enable auto-scroll and jump to bottom immediately
    isAutoScrollActiveRef.current = true
    setShowScrollBottomBtn(false)
    setTimeout(() => scrollToBottom('instant'), 15)

    // 3. Instant optimistic UI feedback at 0ms
    const tempId = `temp-${Date.now()}`
    const optimisticJob: TerminalJob = {
      id: tempId,
      command: trimmed,
      terminal_id: activeTabId,
      status: 'running',
      output: '',
      cwd: currentCwd,
      process_running: true,
    }

    setJobs((prev) => [...prev, optimisticJob])
    setRunningJobId(tempId)
    setCommandHistory((prev) => [...prev, trimmed])
    setHistoryIndex(-1)
    setCommandInput('')
    setErrorMsg('')

    try {
      // 4. Dispatch to backend
      const returnedJob: TerminalJob = await workspaceRequest('/terminal/jobs', {
        method: 'POST',
        body: JSON.stringify({
          command: trimmed,
          terminal_id: activeTabId,
        }),
      })

      // Replace optimistic placeholder with real result immediately
      setJobs((prev) => prev.map((j) => (j.id === tempId ? returnedJob : j)))

      if (returnedJob.status === 'running') {
        setRunningJobId(returnedJob.id)
      } else {
        setRunningJobId(null)
        const isError =
          returnedJob.status === 'failed' ||
          (returnedJob.exit_code != null && returnedJob.exit_code !== 0) ||
          Boolean((returnedJob as any).sentry_event_id)
        if (isError && onErrorCaptured) {
          onErrorCaptured({
            id: returnedJob.id,
            command: returnedJob.command,
            output: returnedJob.output,
            exit_code: returnedJob.exit_code,
            sentry_event_id: (returnedJob as any).sentry_event_id,
          })
        }
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Command execution failed')
      setJobs((prev) =>
        prev.map((j) =>
          j.id === tempId
            ? { ...j, status: 'failed', exit_code: 1, output: 'Failed to dispatch command to cloud container' }
            : j
        )
      )
      setRunningJobId(null)
    }
  }

  // Stop running command
  const handleStopCommand = async () => {
    if (!runningJobId) return
    try {
      await workspaceRequest(`/terminal/jobs/${runningJobId}`, { method: 'DELETE' })
      const updated = await workspaceRequest('/terminal/jobs')
      setJobs(updated)
      setRunningJobId(null)
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to stop command')
    }
  }

  // Handle arrow key history
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (commandHistory.length === 0) return
      const nextIndex = historyIndex === -1 ? commandHistory.length - 1 : Math.max(0, historyIndex - 1)
      setHistoryIndex(nextIndex)
      setCommandInput(commandHistory[nextIndex])
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (historyIndex === -1) return
      const nextIndex = historyIndex + 1
      if (nextIndex >= commandHistory.length) {
        setHistoryIndex(-1)
        setCommandInput('')
      } else {
        setHistoryIndex(nextIndex)
        setCommandInput(commandHistory[nextIndex])
      }
    }
  }

  const currentTab = tabs.find((t) => t.id === activeTabId) || tabs[0]

  return (
    <div
      className={`border-t border-white/10 bg-[#070a0f] flex flex-col transition-all duration-200 select-text ${
        isMinimized
          ? 'h-9 shrink-0'
          : isExpanded
          ? 'h-[520px] shrink-0'
          : 'h-80 shrink-0'
      }`}
    >
      {/* 1. TERMINAL HEADER BAR */}
      <div className="h-9 shrink-0 flex items-center justify-between border-b border-white/[0.08] bg-[#0c1017] px-2.5">
        {/* Left: Terminal Tabs */}
        <div className="flex items-center gap-1 overflow-x-auto no-scrollbar">
          <div className="flex items-center gap-1.5 px-2 text-slate-400 text-xs font-medium">
            <TerminalIcon className="size-3.5 text-cyan-400" />
            <span className="hidden sm:inline text-[11px] text-slate-400">Terminal</span>
          </div>

          <div className="flex items-center gap-1">
            {tabs.map((tab) => {
              const isActive = tab.id === activeTabId
              const isAi = tab.type === 'ai'
              return (
                <button
                  key={tab.id}
                  onClick={() => {
                    setActiveTabId(tab.id)
                    if (isMinimized) setIsMinimized(false)
                    setTimeout(() => inputRef.current?.focus(), 50)
                  }}
                  className={`group flex items-center gap-1.5 rounded-t px-2.5 py-1 text-xs font-mono transition-colors ${
                    isActive
                      ? isAi
                        ? 'bg-purple-950/60 text-purple-200 border-b-2 border-purple-400'
                        : 'bg-[#151c28] text-cyan-300 border-b-2 border-cyan-400'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
                  }`}
                >
                  {isAi && <Sparkles className="size-3 text-purple-400" />}
                  <span>{tab.title}</span>
                  {tabs.length > 1 && (
                    <span
                      onClick={(e) => handleCloseTab(tab.id, e)}
                      className="ml-0.5 rounded p-0.5 opacity-0 group-hover:opacity-100 hover:bg-white/10 text-slate-400 hover:text-white"
                      title="Close Terminal"
                    >
                      <X className="size-2.5" />
                    </span>
                  )}
                </button>
              )
            })}

            {/* Plus Icon to Add New Terminal Tab */}
            <button
              onClick={handleAddTab}
              className="flex items-center justify-center size-6 rounded hover:bg-white/10 text-slate-400 hover:text-white transition-colors ml-0.5"
              title="New Terminal Tab (CMD)"
            >
              <Plus className="size-3.5" />
            </button>
          </div>
        </div>

        {/* Right: Cloud Status & Controls */}
        <div className="flex items-center gap-2">
          {/* Azure Sandbox Badge */}
          <div className="hidden sm:flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-[10px] text-emerald-400 font-mono">
            <span className="size-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span>Azure Cloud Sandbox</span>
          </div>

          {/* Running Job Stop Button */}
          {runningJobId && (
            <button
              onClick={handleStopCommand}
              className="flex items-center gap-1 px-2 py-0.5 rounded bg-red-500/20 border border-red-500/30 text-red-300 hover:bg-red-500/30 text-[11px] font-mono transition-colors"
              title="Stop running command"
            >
              <Square className="size-2.5 fill-current" />
              <span>Stop</span>
            </button>
          )}

          {/* Clear Button */}
          <button
            onClick={handleClear}
            className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-white/[0.06] transition-colors"
            title="Clear terminal output (or type cls)"
          >
            <Trash2 className="size-3.5" />
          </button>

          {/* Maximize / Normal Size Toggle */}
          <button
            onClick={() => {
              if (isMinimized) setIsMinimized(false)
              setIsExpanded(!isExpanded)
            }}
            className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-white/[0.06] transition-colors"
            title={isExpanded ? 'Restore size' : 'Maximize terminal'}
          >
            {isExpanded ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
          </button>

          {/* Minimize / Expand Toggle */}
          <button
            onClick={() => setIsMinimized(!isMinimized)}
            className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-white/[0.06] transition-colors"
            title={isMinimized ? 'Expand terminal' : 'Minimize terminal'}
          >
            {isMinimized ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
          </button>
        </div>
      </div>

      {/* 2. TERMINAL BODY */}
      {!isMinimized && (
        <div className="flex-1 flex flex-col bg-[#05080e] overflow-hidden font-mono text-xs relative">
          {/* Floating Scroll to Latest Button */}
          {showScrollBottomBtn && (
            <button
              onClick={() => {
                isAutoScrollActiveRef.current = true
                setShowScrollBottomBtn(false)
                scrollToBottom('smooth')
              }}
              className="absolute bottom-12 right-4 z-20 flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-cyan-600/90 hover:bg-cyan-500 text-white text-[11px] font-mono shadow-lg shadow-black/60 transition-all border border-cyan-400/40 animate-bounce"
            >
              <ArrowDownCircle className="size-3.5" />
              <span>Scroll to latest</span>
            </button>
          )}

          {/* Output Console */}
          <div
            ref={consoleContainerRef}
            onScroll={handleScroll}
            className="flex-1 overflow-y-auto p-3 space-y-2.5 selection:bg-cyan-500/30"
          >
            {/* Environment Banner */}
            <div className="text-[11px] text-slate-500 leading-relaxed border-b border-white/[0.06] pb-2">
              <span className="text-cyan-400 font-semibold">Microsoft Azure Cloud Sandbox</span> · Linux Container (Central India)
              <br />
              <span className="text-slate-400">Current Directory:</span>{' '}
              <span className="text-cyan-200 font-semibold">{displayPromptDir}</span>
              <br />
              <span className="text-slate-500">
                Commands run live in Azure. Type <code className="text-slate-300">cls</code> to clear,{' '}
                <code className="text-slate-300">ls</code> to list folders.
              </span>
            </div>

            {/* If terminal execution disabled */}
            {!terminalEnabled && (
              <div className="rounded border border-amber-500/20 bg-amber-500/10 p-2 text-xs text-amber-300">
                Command execution is currently disabled or initializing on Azure. Please wait...
              </div>
            )}

            {/* Error banner */}
            {errorMsg && (
              <div className="flex items-center gap-1.5 rounded border border-red-500/20 bg-red-500/10 p-2 text-xs text-red-300">
                <AlertCircle className="size-3.5 shrink-0" />
                <span>{errorMsg}</span>
              </div>
            )}

            {/* List of Command Executions for Active Tab */}
            {activeTabJobs.map((job) => {
              const jobDisplayDir = formatCwd(job.cwd)
              const hasDirError =
                job.output &&
                (job.output.includes('Directory does not exist') ||
                  job.output.includes('No such file or directory') ||
                  job.output.includes('cannot access'))

              return (
                <div key={job.id} className="space-y-1">
                  {/* Command Prompt Line */}
                  <div className="flex items-center gap-2 text-slate-400">
                    <span className="text-emerald-400 font-bold">azure@sandbox</span>
                    <span className="text-slate-600">:</span>
                    <span className="text-cyan-400 font-semibold">{jobDisplayDir}</span>
                    <span className="text-slate-300">$</span>
                    <span className="text-slate-100 font-semibold">{job.command}</span>

                    {/* Status Indicator */}
                    <span className="ml-auto flex items-center gap-1 text-[10px]">
                      {job.status === 'running' ? (
                        <span className="flex items-center gap-1 text-cyan-300 bg-cyan-950/80 px-1.5 py-0.5 rounded border border-cyan-800 animate-pulse">
                          <Loader2 className="size-2.5 animate-spin" />
                          running
                        </span>
                      ) : job.status === 'succeeded' ? (
                        <span className="flex items-center gap-1 text-emerald-400 bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-800/60">
                          <CheckCircle2 className="size-2.5" />
                          exit: 0
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-red-400 bg-red-950/60 px-1.5 py-0.5 rounded border border-red-800/60">
                          <AlertCircle className="size-2.5" />
                          exit: {job.exit_code ?? 1}
                        </span>
                      )}
                    </span>
                  </div>

                  {/* Output text */}
                  {job.output && (
                    <pre className="whitespace-pre-wrap rounded bg-black/40 p-2 text-[11px] leading-relaxed text-slate-300 border border-white/[0.04]">
                      {job.output}
                    </pre>
                  )}

                  {/* Smart hint if user typed a folder name that wasn't found */}
                  {hasDirError && (
                    <div className="flex items-center gap-1.5 text-[11px] text-amber-300/80 pl-2">
                      <Info className="size-3 text-amber-400 shrink-0" />
                      <span>
                        Tip: Linux is case-sensitive. Check the explorer or type{' '}
                        <code className="text-amber-200 underline cursor-pointer" onClick={() => setCommandInput('ls')}>ls</code> to see exact folder names.
                      </span>
                    </div>
                  )}

                  {/* Notices */}
                  {job.notices && job.notices.length > 0 && (
                    <div className="space-y-0.5">
                      {job.notices.map((n) => (
                        <p key={n.id} className="text-[10px] text-slate-500 italic">
                          {n.text}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {/* 3. COMMAND INPUT FORM */}
          <form
            onSubmit={handleRunCommand}
            className="shrink-0 flex items-center gap-2 border-t border-white/[0.08] bg-[#090d15] px-3 py-2"
          >
            {/* Dynamic Prompt Symbol with Current CWD */}
            <div className="flex items-center gap-1.5 select-none text-[11px] shrink-0 font-mono">
              <span className="text-emerald-400 font-bold">azure@sandbox</span>
              <span className="text-slate-600">:</span>
              <span className="text-cyan-400 font-semibold">{displayPromptDir}</span>
              <span className="text-slate-300 font-bold">$</span>
            </div>

            {/* Input Line: Disabled for AI-managed tab, interactive for user tabs */}
            {currentTab.type === 'ai' ? (
              <div className="flex-1 flex items-center gap-2 py-1 text-xs text-purple-300 font-mono italic select-none">
                <span className="inline-block size-2 rounded-full bg-purple-400 animate-pulse shrink-0" />
                <span>AI Terminal is system-managed (automated agent execution only · non-interactive)</span>
              </div>
            ) : (
              <input
                ref={inputRef}
                type="text"
                value={commandInput}
                onChange={(e) => setCommandInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  terminalEnabled
                    ? `Run command in ${currentTab.title} (e.g. ls, cd UniversityManagementSystem-GUI, cls)...`
                    : 'Terminal disabled'
                }
                disabled={!terminalEnabled}
                className="min-w-0 flex-1 bg-transparent text-xs text-white placeholder-slate-600 focus:outline-none font-mono"
              />
            )}

            {/* Submit Run Button */}
            {currentTab.type !== 'ai' && (
              <button
                type="submit"
                disabled={!commandInput.trim() || !terminalEnabled}
                className="flex items-center gap-1 rounded bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 px-2.5 py-1 text-[11px] font-mono transition-colors disabled:opacity-40"
              >
                <Play className="size-2.5 fill-current" />
                <span>Run</span>
              </button>
            )}
          </form>
        </div>
      )}
    </div>
  )
}
