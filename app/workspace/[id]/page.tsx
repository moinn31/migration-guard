'use client'

import React, { useEffect, useState, useMemo } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { UserButton, useAuth } from '@clerk/nextjs'
import {
  Folder,
  FolderOpen,
  FileCode,
  FileText,
  FileJson,
  ChevronRight,
  ChevronDown,
  Search,
  Copy,
  Check,
  Download,
  GitBranch,
  Terminal,
  Send,
  Sparkles,
  ArrowLeft,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Code2,
  Eye,
  Sliders,
  Layers,
  File as FileIcon,
} from 'lucide-react'
import { authenticatedFetch } from '@/lib/api/client'
import { isolatedPreviewUrl } from '@/lib/preview'
import { WorkspaceTerminal } from '@/components/workspace-terminal'

interface FileItem {
  id: string
  path: string
  size_bytes: number
  is_binary: boolean
}

interface TreeNode {
  name: string
  path: string
  isFolder: boolean
  children: Record<string, TreeNode>
  file?: FileItem
}

interface NodeAnalysis {
  name?: string
  version?: string
  node_version?: string
  package_manager?: string
  lockfile?: string | null
  frameworks?: string[]
  dependencies?: Record<string, string>
  devDependencies?: Record<string, string>
  scripts?: Record<string, string>
}

interface WorkspaceData {
  project: {
    id: string
    name: string
    repository_url: string
  }
  latest_run?: {
    id: string
    state: string
    status_message: string
    node_analysis?: NodeAnalysis
    default_branch: string
    kind?: 'import' | 'verification'
    verdict?: string | null
  } | null
  files_count: number
  files: FileItem[]
  preview_url?: string | null
  terminal_enabled?: boolean
  verification_enabled?: boolean
  agent_mode?: 'camber' | 'local_analysis'
}

interface ChatMessage {
  role: 'assistant' | 'user' | 'error' | 'warning'
  text: string
  time?: string
  command?: string
  output?: string
  sentryEventId?: string
  exitCode?: number | null
}

export default function WorkspacePage() {
  const { id: projectId } = useParams<{ id: string }>()
  const router = useRouter()
  const { isLoaded, isSignedIn } = useAuth()

  const [loading, setLoading] = useState(true)
  const [workspace, setWorkspace] = useState<WorkspaceData | null>(null)
  const previewUrl = typeof window === 'undefined' ? null : isolatedPreviewUrl(workspace?.preview_url, window.location.origin)
  const [selectedFilePath, setSelectedFilePath] = useState<string>('')
  const [selectedFileContent, setSelectedFileContent] = useState<string>('')
  const [fileLoading, setFileLoading] = useState(false)
  const [fileSearch, setFileSearch] = useState('')
  const [copied, setCopied] = useState(false)
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>({})

  // View mode tab: 'code' | 'preview'
  const [viewMode, setViewMode] = useState<'code' | 'preview'>('code')
  const [previewVersion, setPreviewVersion] = useState(0)
  const [workspaceError, setWorkspaceError] = useState('')
  const [verifying, setVerifying] = useState(false)
  async function startVerification() {
    setVerifying(true)
    setWorkspaceError('')
    try {
      const response = await authenticatedFetch(`${process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000'}/projects/${projectId}/runs`, { method: 'POST' })
      const data = await response.json()
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Unable to start verification')
      await loadWorkspace()
      router.push(`/runs/${data.id}/tests`)
    } catch (error) { setWorkspaceError(error instanceof Error ? error.message : 'Unable to start verification') }
    finally { setVerifying(false) }
  }

  // Chat/Follow-up prompt state
  const [promptInput, setPromptInput] = useState('')
  const [sending, setSending] = useState(false)
  const [commandInput, setCommandInput] = useState('')
  const [terminalError, setTerminalError] = useState('')
  const [jobs, setJobs] = useState<Array<{ id: string; command: string; status: string; output: string; process_running: boolean; notices: Array<{ id: string; text: string }> }>>([])
  async function workspaceRequest(path: string, options: RequestInit = {}) {
    const response = await authenticatedFetch(`${process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000'}/api/projects/${projectId}${path}`, {
      ...options, headers: { 'Content-Type': 'application/json', ...options.headers },
    })
    const data = await response.json()
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Workspace request failed')
    return data
  }
  useEffect(() => {
    if (!isLoaded || !isSignedIn || !workspace?.terminal_enabled) return
    let active = true
    const refresh = async () => {
      try { const data = await workspaceRequest('/terminal/jobs'); if (active) { setJobs(data); setTerminalError('') } }
      catch (error) { if (active) setTerminalError(error instanceof Error ? error.message : 'Unable to load terminal jobs') }
    }
    refresh()
    const timer = setInterval(refresh, 2000)
    return () => { active = false; clearInterval(timer) }
  }, [projectId, isLoaded, isSignedIn, workspace?.terminal_enabled])
  async function startCommand() {
    if (!commandInput.trim()) return
    setTerminalError('')
    try {
      await workspaceRequest('/terminal/jobs', { method: 'POST', body: JSON.stringify({ command: commandInput, terminal_id: `terminal-${Date.now()}` }) })
      setCommandInput('')
      setJobs(await workspaceRequest('/terminal/jobs'))
    } catch (error) { setTerminalError(error instanceof Error ? error.message : 'Unable to start command') }
  }
  async function stopCommand(jobId: string) {
    try { await workspaceRequest(`/terminal/jobs/${jobId}`, { method: 'DELETE' }); setJobs(await workspaceRequest('/terminal/jobs')) }
    catch (error) { setTerminalError(error instanceof Error ? error.message : 'Unable to stop command') }
  }
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      text: 'Workspace assistant. Ask about the imported project or use the terminal below to run a command on the configured worker.',
      time: 'Just now',
    },
  ])
  const alertedJobIdsRef = React.useRef<Set<string>>(new Set())

  // Reset chat and error tracking when project changes
  useEffect(() => {
    setChatMessages([
      {
        role: 'assistant',
        text: 'Workspace assistant. Ask about the imported project or use the terminal below to run a command on the configured worker.',
        time: 'Just now',
      },
    ])
    alertedJobIdsRef.current = new Set()
    setJobs([])
  }, [projectId])

  // Project Lifecycle auto-cleanup:
  // When closing tab, refreshing, or navigating away, automatically kill all terminals & processes for this project
  useEffect(() => {
    if (!projectId) return

    const killProjectTerminals = () => {
      try {
        const url = `${process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000'}/api/projects/${projectId}/terminal/kill-all`
        if (typeof navigator !== 'undefined' && navigator.sendBeacon) {
          navigator.sendBeacon(url)
        } else {
          fetch(url, { method: 'POST', keepalive: true }).catch(() => {})
        }
      } catch (err) {
        // ignore background unload errors
      }
    }

    window.addEventListener('beforeunload', killProjectTerminals)
    window.addEventListener('pagehide', killProjectTerminals)

    return () => {
      window.removeEventListener('beforeunload', killProjectTerminals)
      window.removeEventListener('pagehide', killProjectTerminals)
      killProjectTerminals()
    }
  }, [projectId])

  const handleErrorCaptured = (err: { id: string; command: string; output: string; exit_code?: number | null; sentry_event_id?: string }) => {
    if (alertedJobIdsRef.current.has(err.id)) return
    alertedJobIdsRef.current.add(err.id)

    setChatMessages((prev) => [
      ...prev,
      {
        role: 'error',
        text: err.output || `Command '${err.command}' failed`,
        command: err.command,
        output: err.output,
        sentryEventId: err.sentry_event_id,
        exitCode: err.exit_code,
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ])
  }

  async function handleAskCamberFix(err: ChatMessage) {
    const promptText = `Diagnose and fix command error: \`${err.command}\`\nOutput:\n${err.output || err.text}\n${err.sentryEventId ? `Sentry Event ID: ${err.sentryEventId}` : ''}`
    setChatMessages((prev) => [
      ...prev,
      { role: 'user', text: `Diagnose error in: \`${err.command}\``, time: 'Just now' },
    ])
    setSending(true)
    try {
      const data = await workspaceRequest('/chat', { method: 'POST', body: JSON.stringify({ message: promptText }) })
      setChatMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          text: data.reply,
          time: 'Just now',
        }
      ])
    } catch (error) {
      setChatMessages(prev => [
        ...prev,
        { role: 'assistant', text: error instanceof Error ? error.message : 'Assistant unavailable', time: 'Just now' }
      ])
    } finally { setSending(false) }
  }

  const [runningPipeline, setRunningPipeline] = useState(false)
  const autoStartedRef = React.useRef<Record<string, boolean>>({})

  async function triggerMultiagentPipeline(isAuto = false) {
    if (runningPipeline) return
    setRunningPipeline(true)
    if (!isAuto) {
      setChatMessages((prev) => [
        ...prev,
        {
          role: 'user',
          text: '🚀 Starting Multi-Agent System (Agent 1: Codebase Analyzer, Agent 2: Dependency Installer, Agent 3: Project Runner)...',
          time: 'Just now',
        },
      ])
    }
    try {
      const res = await workspaceRequest('/multiagent/pipeline', { method: 'POST' })
      if (res.already_running) {
        setChatMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            text: `🎉 **[Project Runner]** ${res.message || 'Application dev server is already running! Live Preview is ready.'}`,
            time: 'Just now',
          },
        ])
        return
      }
      if (res.report) {
        setChatMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            text: res.report,
            time: 'Just now',
          },
        ])
      }
      if (res.install_jobs && res.install_jobs.length > 0) {
        setChatMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            text: '🤖 **[Agent 2: Dependency Installer]**\nDependency setup completed in the **AI Terminal**. Live installation verified inside Azure Container sandbox.',
            time: 'Just now',
          },
        ])
      }
      if (res.run_job) {
        setChatMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            text: '🎉 **[Agent 3: Project Runner]**\nApplication launch command executed! Switched to **Preview** tab to interact with your live running project.',
            time: 'Just now',
          },
        ])
      }
    } catch (err) {
      if (!isAuto) {
        setChatMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            text: `Multi-agent pipeline error: ${err instanceof Error ? err.message : 'Unknown error'}`,
            time: 'Just now',
          },
        ])
      }
    } finally {
      setRunningPipeline(false)
    }
  }

  // 1. Load Workspace & Files from Backend (Neon DB)
  async function loadWorkspace() {
    try {
      const res = await authenticatedFetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000'}/api/projects/${projectId}/workspace`,
      )
      if (res.ok) {
        const data: WorkspaceData = await res.json()
        setWorkspace(data)
        setWorkspaceError('')

        // Auto-run project on open (if not already running)
        if (!autoStartedRef.current[projectId]) {
          autoStartedRef.current[projectId] = true
          setTimeout(() => {
            triggerMultiagentPipeline(true)
          }, 800)
        }

        // Select initial file (e.g. package.json or README.md or first file)
        if (!selectedFilePath && data.files && data.files.length > 0) {
          const defaultFile =
            data.files.find((f) => f.path === 'package.json') ||
            data.files.find((f) => f.path.toLowerCase().includes('readme')) ||
            data.files[0]
          if (defaultFile) {
            setSelectedFilePath(defaultFile.path)
            loadFileContent(defaultFile.path)
          }
        }
      } else setWorkspaceError('Unable to load this workspace. Refresh your sign-in session and retry.')
    } catch (err) {
      console.error('Failed to load workspace:', err)
      setWorkspaceError('Unable to reach the workspace API.')
    } finally {
      setLoading(false)
    }
  }

  // 2. Load File Content from Neon DB
  async function loadFileContent(path: string) {
    setFileLoading(true)
    try {
      const res = await authenticatedFetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000'}/api/projects/${projectId}/files/content?path=${encodeURIComponent(path)}`,
      )
      if (res.ok) {
        const data = await res.json()
        setSelectedFileContent(data.content ?? '(Empty file or binary format)')
      } else {
        setSelectedFileContent('// Unable to load file content')
      }
    } catch (err) {
      console.error('Error reading file content:', err)
      setSelectedFileContent('// Error loading file from database')
    } finally {
      setFileLoading(false)
    }
  }

  // Poll workspace every 3 seconds while run state is not COMPLETED/FAILED
  useEffect(() => {
    if (!isLoaded || !isSignedIn) return
    loadWorkspace()
    const interval = setInterval(() => {
      if (workspace?.latest_run?.state && ['COMPLETED', 'FAILED', 'INCONCLUSIVE', 'AWAITING_APPROVAL', 'ACCEPTED', 'REJECTED'].includes(workspace.latest_run.state)) {
        return
      }
      loadWorkspace()
    }, 3000)
    return () => clearInterval(interval)
  }, [projectId, workspace?.latest_run?.state, isLoaded, isSignedIn])

  // Select file handler
  function handleSelectFile(path: string) {
    setSelectedFilePath(path)
    loadFileContent(path)
  }

  // Copy code handler
  function handleCopy() {
    if (!selectedFileContent) return
    navigator.clipboard.writeText(selectedFileContent)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Download active file
  function handleDownload() {
    if (!selectedFilePath || !selectedFileContent) return
    const blob = new Blob([selectedFileContent], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = selectedFilePath.split('/').pop() || 'download'
    a.click()
    URL.revokeObjectURL(url)
  }

  // Send message
  async function handleSendPrompt() {
    if (!promptInput.trim() || sending) return
    const userText = promptInput.trim()
    setPromptInput('')
    setChatMessages((prev) => [
      ...prev,
      { role: 'user', text: userText, time: 'Just now' },
    ])
    setSending(true)
    try {
      const data = await workspaceRequest('/chat', { method: 'POST', body: JSON.stringify({ message: userText }) })
      setChatMessages(prev => [...prev, { role: 'assistant', text: data.reply, time: 'Just now' }])
    } catch (error) {
      setChatMessages(prev => [...prev, { role: 'assistant', text: error instanceof Error ? error.message : 'Assistant unavailable', time: 'Just now' }])
    } finally { setSending(false) }
  }

  // Build hierarchical folder tree from flat file list
  const fileTree = useMemo(() => {
    const root: TreeNode = { name: '', path: '', isFolder: true, children: {} }
    if (!workspace?.files) return root

    const filtered = workspace.files.filter((f) =>
      fileSearch ? f.path.toLowerCase().includes(fileSearch.toLowerCase()) : true
    )

    filtered.forEach((file) => {
      const parts = file.path.split('/')
      let current = root
      let currentPath = ''

      parts.forEach((part, index) => {
        currentPath = currentPath ? `${currentPath}/${part}` : part
        const isLast = index === parts.length - 1

        if (isLast) {
          current.children[part] = {
            name: part,
            path: currentPath,
            isFolder: false,
            children: {},
            file,
          }
        } else {
          if (!current.children[part]) {
            current.children[part] = {
              name: part,
              path: currentPath,
              isFolder: true,
              children: {},
            }
          }
          current = current.children[part]
        }
      })
    })

    return root
  }, [workspace?.files, fileSearch])

  // Toggle folder open/collapse
  function toggleFolder(path: string) {
    setExpandedFolders((prev) => ({
      ...prev,
      [path]: prev[path] === undefined ? false : !prev[path],
    }))
  }

  function isFolderOpen(path: string): boolean {
    return expandedFolders[path] !== false // Default open
  }

  // Render tree node recursively
  function renderTreeNode(node: TreeNode, depth = 0) {
    const sortedKeys = Object.keys(node.children).sort((a, b) => {
      const childA = node.children[a]
      const childB = node.children[b]
      if (childA.isFolder && !childB.isFolder) return -1
      if (!childA.isFolder && childB.isFolder) return 1
      return a.localeCompare(b)
    })

    return (
      <div key={node.path} className="select-none">
        {sortedKeys.map((key) => {
          const item = node.children[key]
          const isSelected = item.path === selectedFilePath

          if (item.isFolder) {
            const open = isFolderOpen(item.path)
            return (
              <div key={item.path}>
                <div
                  onClick={() => toggleFolder(item.path)}
                  style={{ paddingLeft: `${depth * 14 + 10}px` }}
                  className="flex items-center gap-1.5 py-1 px-2 text-xs text-slate-400 hover:text-white hover:bg-white/[0.04] rounded cursor-pointer transition-colors"
                >
                  {open ? (
                    <ChevronDown className="size-3.5 text-slate-500 shrink-0" />
                  ) : (
                    <ChevronRight className="size-3.5 text-slate-500 shrink-0" />
                  )}
                  {open ? (
                    <FolderOpen className="size-3.5 text-cyan-400 shrink-0" />
                  ) : (
                    <Folder className="size-3.5 text-slate-400 shrink-0" />
                  )}
                  <span className="truncate">{item.name}</span>
                </div>
                {open && renderTreeNode(item, depth + 1)}
              </div>
            )
          }

          // File icon selection
          let FileTypeIcon = FileIcon
          if (item.name.endsWith('.json')) FileTypeIcon = FileJson
          else if (['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs'].some((e) => item.name.endsWith(e)))
            FileTypeIcon = FileCode
          else if (['.css', '.html', '.md'].some((e) => item.name.endsWith(e))) FileTypeIcon = FileText

          return (
            <div
              key={item.path}
              onClick={() => handleSelectFile(item.path)}
              style={{ paddingLeft: `${depth * 14 + 24}px` }}
              className={`flex items-center gap-2 py-1 px-2 text-xs rounded cursor-pointer transition-colors ${
                isSelected
                  ? 'bg-cyan-500/15 text-cyan-200 font-medium'
                  : 'text-slate-300 hover:text-white hover:bg-white/[0.04]'
              }`}
            >
              <FileTypeIcon
                className={`size-3.5 shrink-0 ${
                  isSelected
                    ? 'text-cyan-300'
                    : item.name.endsWith('.json')
                    ? 'text-amber-400'
                    : item.name.endsWith('.ts') || item.name.endsWith('.tsx')
                    ? 'text-blue-400'
                    : 'text-slate-400'
                }`}
              />
              <span className="truncate">{item.name}</span>
            </div>
          )
        })}
      </div>
    )
  }

  const analysis = workspace?.latest_run?.node_analysis

  return (
    <div className="flex h-screen w-screen flex-col bg-[#0b0f17] text-slate-200 overflow-hidden font-sans">
      {/* 1. TOP NAVBAR */}
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-white/[0.08] bg-[#0d121d] px-4">
        {/* Left: Project title & Back */}
        <div className="flex items-center gap-3">
          <Link
            href="/dashboard"
            className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors"
          >
            <ArrowLeft className="size-3.5" />
          </Link>
          <div className="h-4 w-px bg-white/10" />
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-white tracking-tight">
              {workspace?.project.name ?? 'Loading project...'}
            </span>
            <span className="text-[11px] text-slate-500 font-mono">
              ({workspace?.files_count ?? 0} files in Neon DB)
            </span>
          </div>
        </div>

        {/* Center: Mode Tabs (Preview vs Code) */}
        <div className="flex items-center rounded-lg border border-white/[0.08] bg-black/40 p-0.5">
          <button
            onClick={() => setViewMode('preview')}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-colors ${
              viewMode === 'preview'
                ? 'bg-white/[0.08] text-white'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Eye className="size-3.5" />
            Preview
          </button>
          <button
            onClick={() => setViewMode('code')}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-colors ${
              viewMode === 'code'
                ? 'bg-cyan-500/20 text-cyan-200'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Code2 className="size-3.5 text-cyan-300" />
            Code
          </button>
        </div>

        {/* Right: Branch & Status */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 rounded-md border border-white/[0.08] bg-white/[0.02] px-2.5 py-1 text-xs text-slate-300">
            <GitBranch className="size-3 text-cyan-400" />
            <span>{workspace?.latest_run?.default_branch ?? 'main'}</span>
          </div>

          {/* Status Badge */}
          {workspace?.latest_run?.state === 'COMPLETED' ? (
            <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">
              <CheckCircle2 className="size-3" />
              Synced in Neon DB
            </span>
          ) : (
            <span className="flex items-center gap-1 text-[11px] font-medium text-cyan-300 bg-cyan-500/10 border border-cyan-500/20 px-2 py-0.5 rounded-full animate-pulse">
              {['AWAITING_APPROVAL', 'ACCEPTED', 'REJECTED', 'INCONCLUSIVE', 'FAILED'].includes(workspace?.latest_run?.state ?? '') ? <CheckCircle2 className="size-3" /> : <RefreshCw className="size-3 animate-spin" />}
              {workspace?.latest_run?.state ?? 'SYNCING'}
            </span>
          )}

          <div className="h-4 w-px bg-white/10" />
          <UserButton />
        </div>
      </header>

      {/* 2. MAIN 3-COLUMN WORKSPACE BODY */}
      <div className="flex flex-1 overflow-hidden">
        {/* COLUMN 1 (LEFT): Activity, Changelog & Agent Chat */}
        <aside className="w-80 shrink-0 border-r border-white/[0.08] bg-[#0c101a] flex flex-col justify-between">
          <div className="overflow-y-auto p-4 space-y-4 flex-1">
            {/* Run Progress Status */}
            <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-3 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400 font-medium">{workspace?.latest_run?.kind === 'verification' ? 'Migration verification' : 'Cloning & DB Storage'}</span>
                <span className="text-cyan-300 font-mono text-[10px] bg-cyan-950/80 px-2 py-0.5 rounded border border-cyan-800">
                  {workspace?.latest_run?.state ?? 'INIT'}
                </span>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                {workspace?.latest_run?.status_message || 'Loading project status...'}
              </p>
              {workspace?.verification_enabled && <button onClick={startVerification} disabled={verifying || (workspace?.latest_run?.kind === 'verification' && !['FAILED', 'INCONCLUSIVE', 'AWAITING_APPROVAL', 'ACCEPTED', 'REJECTED'].includes(workspace.latest_run.state))} className="rounded bg-cyan-300 px-3 py-2 text-xs text-black disabled:opacity-40">{verifying ? 'Starting...' : 'Run Java 8 to 17 verification'}</button>}
              {workspace?.latest_run?.kind === 'verification' && <Link href={`/runs/${workspace.latest_run.id}/tests`} className="block text-xs text-cyan-200">View tests and coverage</Link>}
            </div>

            {/* Detected Node.js Specs Card */}
            {analysis && (
              <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-3.5 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-200">Detected Environment</span>
                  <span className="text-[10px] font-mono text-cyan-300 bg-cyan-500/10 px-1.5 py-0.5 rounded">
                    {analysis.package_manager || 'npm'}
                  </span>
                </div>

                <div className="space-y-1.5 text-xs text-slate-300">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Node version:</span>
                    <span className="font-mono text-cyan-200 font-medium">{analysis.node_version}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Lockfile:</span>
                    <span className="font-mono text-slate-300">{analysis.lockfile || 'None'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Dependencies:</span>
                    <span className="font-mono text-slate-300">
                      {Object.keys(analysis.dependencies || {}).length} deps
                    </span>
                  </div>
                </div>

                {/* Frameworks tags */}
                {analysis.frameworks && analysis.frameworks.length > 0 && (
                  <div className="pt-2 border-t border-white/[0.06]">
                    <span className="text-[10px] uppercase tracking-wider text-slate-500 block mb-1.5">
                      Frameworks
                    </span>
                    <div className="flex flex-wrap gap-1">
                      {analysis.frameworks.map((fw) => (
                        <span
                          key={fw}
                          className="text-[10px] bg-white/[0.06] border border-white/10 text-cyan-200 px-2 py-0.5 rounded"
                        >
                          {fw}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Activity Stream */}
            <div className="space-y-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Agent History
              </span>
              <div className="space-y-2 text-xs">
                {chatMessages.map((msg, i) => {
                  if (msg.role === 'error' || msg.role === 'warning') {
                    return (
                      <div
                        key={i}
                        className="rounded-xl border border-red-500/30 bg-red-950/20 p-3 space-y-2 text-xs"
                      >
                        <div className="flex items-center justify-between">
                          <span className="flex items-center gap-1.5 font-semibold text-red-400">
                            <AlertTriangle className="size-3.5 text-red-400 shrink-0" />
                            Command Error
                          </span>
                          {msg.sentryEventId ? (
                            <a
                              href="https://sentry.io"
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-[10px] text-cyan-300 font-mono bg-cyan-950/80 px-1.5 py-0.5 rounded border border-cyan-800 hover:underline flex items-center gap-1"
                              title="Inspect issue in Sentry"
                            >
                              <span>Sentry #{msg.sentryEventId.slice(0, 8)}</span>
                              <span>↗</span>
                            </a>
                          ) : (
                            <span className="text-[10px] text-slate-500 font-mono">
                              exit: {msg.exitCode ?? 1}
                            </span>
                          )}
                        </div>

                        {msg.command && (
                          <div className="rounded bg-black/50 px-2 py-1 font-mono text-[11px] text-slate-300 border border-white/5 truncate">
                            <span className="text-emerald-400">$ </span>
                            {msg.command}
                          </div>
                        )}

                        <p className="whitespace-pre-wrap font-mono text-[11px] text-red-300/90 leading-relaxed max-h-24 overflow-y-auto bg-black/30 p-2 rounded border border-red-500/10">
                          {msg.output || msg.text}
                        </p>

                        <button
                          onClick={() => handleAskCamberFix(msg)}
                          disabled={sending}
                          className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-purple-500/20 hover:bg-purple-500/30 border border-purple-500/40 py-1.5 text-xs text-purple-200 font-medium transition-colors disabled:opacity-40"
                        >
                          <Sparkles className="size-3.5 text-purple-300" />
                          <span>Analyze & Fix with Camber Agent</span>
                        </button>

                        {msg.time && (
                          <span className="text-[10px] text-slate-500 block text-right">
                            {msg.time}
                          </span>
                        )}
                      </div>
                    )
                  }

                  return (
                    <div
                      key={i}
                      className={`rounded-lg p-2.5 ${
                        msg.role === 'assistant'
                          ? 'bg-white/[0.03] border border-white/[0.06] text-slate-300'
                          : 'bg-cyan-500/10 border border-cyan-500/20 text-cyan-100 ml-3'
                      }`}
                    >
                      <p className="whitespace-pre-wrap leading-relaxed">{msg.text}</p>
                      {msg.time && (
                        <span className="text-[10px] text-slate-500 block mt-1 text-right">{msg.time}</span>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          </div>

          {/* Chat / Prompt Input Form */}
          <div className="p-3 border-t border-white/[0.08] bg-[#090d14]">
            {/* 3-Agent Automation Launch Button */}
            <button
              onClick={triggerMultiagentPipeline}
              disabled={runningPipeline}
              className="w-full mb-2.5 flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500/20 to-purple-500/20 hover:from-cyan-500/30 hover:to-purple-500/30 border border-cyan-500/40 py-2 px-3 text-xs text-cyan-200 font-semibold shadow-lg transition-all disabled:opacity-40"
            >
              <Sparkles className={`size-3.5 text-cyan-300 ${runningPipeline ? 'animate-spin' : ''}`} />
              <span>{runningPipeline ? 'Agents Working on Project…' : '🤖 Launch Multi-Agent System (3 Agents)'}</span>
            </button>

            <p className="mb-2 text-[10px] text-slate-400">{workspace?.agent_mode === 'camber' ? 'Connected AI assistant · suggestions require review' : 'Local project analysis · no external AI required'}</p>
            <div className="mb-3 flex flex-wrap gap-1.5">{['Explain this project', 'Plan the Java 8 to Java 17 migration', 'Summarize verification results and coverage'].map(prompt => <button key={prompt} onClick={() => setPromptInput(prompt)} className="rounded border border-white/10 px-2 py-1 text-left text-[10px] text-cyan-200">{prompt}</button>)}</div>
            <div className="relative">
              <textarea
                value={promptInput}
                onChange={(e) => setPromptInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleSendPrompt()
                  }
                }}
                placeholder="Ask a follow-up or migration command..."
                rows={2}
                className="w-full resize-none rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-cyan-400 focus:outline-none"
              />
              <button
                onClick={handleSendPrompt}
                disabled={!promptInput.trim() || sending}
                className="absolute right-2.5 bottom-3.5 text-cyan-400 hover:text-cyan-200 disabled:opacity-40 transition-colors"
              >
                <Send className="size-3.5" />
              </button>
            </div>
            <div className="flex items-center justify-between mt-2 text-[10px] text-slate-500">
              <span className="flex items-center gap-1">
                <Sparkles className="size-3 text-cyan-400" />
                {sending ? 'Assistant responding…' : 'AI Migration Assistant'}
              </span>
              <span>Enter to send</span>
            </div>
          </div>
        </aside>

        {/* COLUMN 2 (MIDDLE): File Explorer Tree */}
        <aside className="w-64 shrink-0 border-r border-white/[0.08] bg-[#090d15] flex flex-col">
          <div className="p-3 border-b border-white/[0.08] flex items-center justify-between">
            <span className="text-xs font-semibold text-white tracking-wide uppercase">Files</span>
            <span className="text-[10px] font-mono text-slate-500">{workspace?.files_count ?? 0} items</span>
          </div>

          {/* File Search */}
          <div className="p-2 border-b border-white/[0.06]">
            <div className="relative">
              <Search className="size-3.5 text-slate-500 absolute left-2.5 top-2.5" />
              <input
                type="text"
                value={fileSearch}
                onChange={(e) => setFileSearch(e.target.value)}
                placeholder="Filter files..."
                className="w-full rounded-md border border-white/[0.08] bg-black/40 py-1.5 pl-8 pr-2 text-xs text-white placeholder-slate-500 focus:border-cyan-400 focus:outline-none"
              />
            </div>
          </div>

          {/* Tree View */}
          <div className="flex-1 overflow-y-auto p-1.5 py-2 space-y-0.5">
            {workspace?.files && workspace.files.length > 0 ? (
              renderTreeNode(fileTree)
            ) : loading ? (
              <div className="flex items-center justify-center p-8 text-xs text-slate-500 gap-2">
                <RefreshCw className="size-3.5 animate-spin" />
                Cloning and reading files...
              </div>
            ) : (
              <div className="p-6 text-center text-xs text-slate-500">No files found.</div>
            )}
          </div>
        </aside>

        {/* COLUMN 3 (RIGHT): Code Editor / Viewer */}
        <main className="flex-1 flex flex-col bg-[#080b11] overflow-hidden">
          {/* Active File Header */}
          <div className="flex h-10 shrink-0 items-center justify-between border-b border-white/[0.08] bg-[#0c1018] px-4">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono font-medium text-cyan-200">
                {selectedFilePath || 'Select a file to inspect'}
              </span>
            </div>

            {selectedFilePath && (
              <div className="flex items-center gap-2">
                <button
                  onClick={handleCopy}
                  className="flex items-center gap-1 rounded border border-white/10 px-2 py-1 text-[11px] text-slate-300 hover:text-white hover:bg-white/[0.05] transition-colors"
                  title="Copy code"
                >
                  {copied ? <Check className="size-3 text-emerald-400" /> : <Copy className="size-3" />}
                  {copied ? 'Copied' : 'Copy'}
                </button>
                <button
                  onClick={handleDownload}
                  className="flex items-center gap-1 rounded border border-white/10 px-2 py-1 text-[11px] text-slate-300 hover:text-white hover:bg-white/[0.05] transition-colors"
                  title="Download file"
                >
                  <Download className="size-3" />
                </button>
              </div>
            )}
          </div>

          {workspaceError && <p role="alert" className="p-4 text-sm text-red-300">{workspaceError}</p>}
          {viewMode === 'preview' ? <section className="flex min-h-0 flex-1 flex-col" aria-label="Application preview">
            {previewUrl ? <>
              <div className="flex items-center justify-between gap-3 border-b border-white/10 p-3 text-xs text-slate-300">
                <span className="truncate">{previewUrl}</span>
                <div className="flex shrink-0 gap-3"><button onClick={() => setPreviewVersion(value => value + 1)}>Reload preview</button><a href={previewUrl} target="_blank" rel="noopener noreferrer">Open in new tab</a></div>
              </div>
              <iframe key={previewVersion} src={previewUrl} title={`${workspace?.project.name} application preview`} sandbox="allow-scripts allow-forms allow-same-origin allow-popups allow-modals allow-downloads" referrerPolicy="no-referrer" className="min-h-96 w-full flex-1 border-0 bg-white" />
            </> : <div className="p-8 text-sm text-slate-400">No application preview is running for this project. Ask the assistant how to start the application on a preview worker.</div>}
          </section> : <>
          {/* Code Body with Line Numbers or Media Viewer */}
          <div className="flex-1 overflow-auto p-4 font-mono text-xs leading-relaxed">
            {fileLoading ? (
              <div className="flex items-center justify-center h-full text-slate-500 gap-2">
                <RefreshCw className="size-4 animate-spin text-cyan-400" />
                Fetching file...
              </div>
            ) : /\.(png|jpe?g|gif|svg|webp|ico|bmp)$/i.test(selectedFilePath) ? (
              <div className="flex flex-col items-center justify-center h-full p-6">
                <div className="p-4 bg-black/40 rounded-xl border border-white/10 shadow-2xl flex flex-col items-center max-w-full">
                  <img
                    src={`${process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000'}/api/projects/${projectId}/files/raw?path=${encodeURIComponent(selectedFilePath)}`}
                    alt={selectedFilePath}
                    className="max-h-[60vh] max-w-full object-contain rounded"
                  />
                  <div className="mt-4 flex items-center justify-between w-full px-2 text-xs text-slate-400">
                    <span className="font-mono truncate">{selectedFilePath}</span>
                    <a
                      href={`${process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000'}/api/projects/${projectId}/files/raw?path=${encodeURIComponent(selectedFilePath)}`}
                      download
                      target="_blank"
                      rel="noreferrer"
                      className="text-cyan-400 hover:underline shrink-0 ml-4 font-sans font-medium"
                    >
                      Download original
                    </a>
                  </div>
                </div>
              </div>
            ) : /\.(mp4|webm|ogg|mov)$/i.test(selectedFilePath) ? (
              <div className="flex flex-col items-center justify-center h-full p-6">
                <div className="p-4 bg-black/40 rounded-xl border border-white/10 shadow-2xl flex flex-col items-center max-w-full">
                  <video
                    src={`${process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000'}/api/projects/${projectId}/files/raw?path=${encodeURIComponent(selectedFilePath)}`}
                    controls
                    className="max-h-[60vh] max-w-full rounded"
                  />
                  <div className="mt-4 flex items-center justify-between w-full px-2 text-xs text-slate-400">
                    <span className="font-mono truncate">{selectedFilePath}</span>
                    <a
                      href={`${process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000'}/api/projects/${projectId}/files/raw?path=${encodeURIComponent(selectedFilePath)}`}
                      download
                      target="_blank"
                      rel="noreferrer"
                      className="text-cyan-400 hover:underline shrink-0 ml-4 font-sans font-medium"
                    >
                      Download video
                    </a>
                  </div>
                </div>
              </div>
            ) : /\.pdf$/i.test(selectedFilePath) ? (
              <div className="flex flex-col h-full w-full rounded-lg overflow-hidden border border-white/10">
                <div className="p-2.5 bg-black/40 border-b border-white/10 flex items-center justify-between text-xs text-slate-400 px-4">
                  <span className="font-mono">{selectedFilePath}</span>
                  <a
                    href={`${process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000'}/api/projects/${projectId}/files/raw?path=${encodeURIComponent(selectedFilePath)}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-cyan-400 hover:underline font-sans font-medium"
                  >
                    Open in new tab
                  </a>
                </div>
                <iframe
                  src={`${process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000'}/api/projects/${projectId}/files/raw?path=${encodeURIComponent(selectedFilePath)}`}
                  className="flex-1 w-full h-full border-0 bg-white"
                  title={selectedFilePath}
                />
              </div>
            ) : selectedFileContent ? (
              <div className="flex">
                {/* Line Numbers */}
                <div className="select-none pr-4 text-right text-slate-600 font-mono text-xs">
                  {selectedFileContent.split('\n').map((_, index) => (
                    <div key={index}>{index + 1}</div>
                  ))}
                </div>

                {/* Code Content */}
                <pre className="flex-1 overflow-x-auto text-slate-200 font-mono text-xs whitespace-pre">
                  <code>{selectedFileContent}</code>
                </pre>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-slate-500 space-y-2">
                <FileCode className="size-8 text-slate-600" />
                <span>Select a file from the explorer to view its code</span>
              </div>
            )}
          </div>
          </>}
          <WorkspaceTerminal
            projectId={projectId}
            terminalEnabled={Boolean(workspace?.terminal_enabled)}
            workspaceRequest={workspaceRequest}
            onErrorCaptured={handleErrorCaptured}
          />
        </main>
      </div>
    </div>
  )
}
