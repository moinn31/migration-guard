'use client'

import { useEffect, useState, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import {
  GitBranch,
  Globe,
  Lock,
  Search,
  Star,
  ExternalLink,
  Plus,
  RefreshCw,
  AlertCircle,
  KeyRound,
  CheckCircle2,
  FolderGit2,
} from 'lucide-react'
import { AppShell, PageHeader } from '@/components/app-shell'
import { api } from '@/lib/api/client'

interface GithubRepo {
  id: number
  name: string
  full_name: string
  private: boolean
  html_url: string
  clone_url: string
  description: string | null
  language: string | null
  stargazers_count: number
  forks_count: number
  updated_at: string
  default_branch: string
  owner: {
    login: string
    avatar_url: string
  }
}

interface GithubUser {
  login: string
  name: string | null
  avatar_url: string
  html_url: string
  public_repos: number
  total_private_repos?: number
}

const LANGUAGE_COLORS: Record<string, string> = {
  Java: '#b07219',
  TypeScript: '#3178c6',
  JavaScript: '#f1e05a',
  Python: '#3572A5',
  HTML: '#e34c26',
  CSS: '#563d7c',
  Go: '#00ADD8',
  Rust: '#dea584',
  C: '#555555',
  'C++': '#f34b7d',
  'C#': '#178600',
  Ruby: '#701516',
  PHP: '#4F5D95',
  Kotlin: '#A97BFF',
  Swift: '#F05138',
}

export default function NewProjectPage() {
  const router = useRouter()

  // Tab: 'github' | 'manual'
  const [activeTab, setActiveTab] = useState<'github' | 'manual'>('github')

  // GitHub state
  const [loading, setLoading] = useState(true)
  const [connected, setConnected] = useState(false)
  const [repos, setRepos] = useState<GithubRepo[]>([])
  const [githubUser, setGithubUser] = useState<GithubUser | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [visibilityFilter, setVisibilityFilter] = useState<'all' | 'public' | 'private'>('all')
  const [selectedLanguage, setSelectedLanguage] = useState<string>('all')

  // Token input state (for PAT fallback)
  const [tokenInput, setTokenInput] = useState('')
  const [showTokenInput, setShowTokenInput] = useState(false)

  // Manual project creation
  const [manualName, setManualName] = useState('')
  const [manualUrl, setManualUrl] = useState('')
  const [manualError, setManualError] = useState('')
  const [importingRepoId, setImportingRepoId] = useState<number | null>(null)

  // Load repositories from /api/github/repos
  async function fetchRepos(customToken?: string) {
    setLoading(true)
    try {
      const headers: Record<string, string> = {}
      const token = customToken || localStorage.getItem('migrationguard_github_token') || ''
      if (token) headers['x-github-token'] = token

      const res = await fetch('/api/github/repos', { headers })
      const data = await res.json()

      if (data.connected && Array.isArray(data.repos)) {
        setConnected(true)
        setRepos(data.repos)
        setGithubUser(data.user)
      } else {
        setConnected(false)
        setRepos([])
      }
    } catch (err) {
      console.error('Failed to load GitHub repositories:', err)
      setConnected(false)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchRepos()
  }, [])

  function handleSaveToken() {
    if (!tokenInput.trim()) return
    localStorage.setItem('migrationguard_github_token', tokenInput.trim())
    setShowTokenInput(false)
    fetchRepos(tokenInput.trim())
  }

  // Import selected repository
  async function handleImportRepo(repo: GithubRepo) {
    setImportingRepoId(repo.id)
    try {
      const { data, error } = await api.POST('/projects', {
        body: {
          name: repo.name,
          repository_url: repo.html_url,
        },
      })
      if (data) {
        router.push(`/projects/${data.id}/new`)
      } else {
        alert(error ? 'Failed to create project: ' + JSON.stringify(error) : 'Unable to create project.')
      }
    } catch (err) {
      console.error(err)
      alert('Error importing project.')
    } finally {
      setImportingRepoId(null)
    }
  }

  // Manual creation submit
  async function handleManualSubmit() {
    if (!manualName.trim()) return
    setManualError('')
    try {
      const { data } = await api.POST('/projects', {
        body: {
          name: manualName.trim(),
          repository_url: manualUrl.trim() || null,
        },
      })
      if (data) {
        router.push(`/projects/${data.id}/new`)
      } else {
        setManualError('Unable to create project.')
      }
    } catch {
      setManualError('Error creating project.')
    }
  }

  // Filter repositories
  const filteredRepos = useMemo(() => {
    return repos.filter((r) => {
      // Visibility filter
      if (visibilityFilter === 'private' && !r.private) return false
      if (visibilityFilter === 'public' && r.private) return false

      // Language filter
      if (selectedLanguage !== 'all' && r.language !== selectedLanguage) return false

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase()
        const matchName = r.name.toLowerCase().includes(q) || r.full_name.toLowerCase().includes(q)
        const matchDesc = r.description?.toLowerCase().includes(q) || false
        if (!matchName && !matchDesc) return false
      }

      return true
    })
  }, [repos, searchQuery, visibilityFilter, selectedLanguage])

  // Get unique languages for filter
  const availableLanguages = useMemo(() => {
    const set = new Set<string>()
    repos.forEach((r) => {
      if (r.language) set.add(r.language)
    })
    return Array.from(set).sort()
  }, [repos])

  return (
    <AppShell>
      <PageHeader eyebrow="Workspace" title="New Project" />

      <div className="space-y-6 p-6 lg:p-10">
        {/* Navigation Tabs */}
        <div className="flex border-b border-white/[0.08]">
          <button
            onClick={() => setActiveTab('github')}
            className={`flex items-center gap-2 border-b-2 px-5 py-3 text-sm font-medium transition-colors ${
              activeTab === 'github'
                ? 'border-cyan-300 text-cyan-200'
                : 'border-transparent text-slate-400 hover:text-white'
            }`}
          >
            <FolderGit2 className="size-4" />
            GitHub Repositories
            {connected && <span className="rounded-full bg-cyan-400/10 px-2 py-0.5 text-xs text-cyan-300">{repos.length}</span>}
          </button>
          <button
            onClick={() => setActiveTab('manual')}
            className={`flex items-center gap-2 border-b-2 px-5 py-3 text-sm font-medium transition-colors ${
              activeTab === 'manual'
                ? 'border-cyan-300 text-cyan-200'
                : 'border-transparent text-slate-400 hover:text-white'
            }`}
          >
            <Plus className="size-4" />
            Custom Repository URL
          </button>
        </div>

        {activeTab === 'github' ? (
          <div className="space-y-6">
            {/* GitHub Connection Status Header */}
            <div className="flex flex-col justify-between gap-4 rounded-2xl border border-white/[0.08] bg-white/[0.035] p-5 sm:flex-row sm:items-center">
              <div className="flex items-center gap-3.5">
                {githubUser?.avatar_url ? (
                  <img
                    src={githubUser.avatar_url}
                    alt={githubUser.login}
                    className="size-10 rounded-full border border-white/10"
                  />
                ) : (
                  <div className="flex size-10 items-center justify-center rounded-xl bg-white/10 text-white">
                    <FolderGit2 className="size-5" />
                  </div>
                )}
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-white">
                      {connected ? (githubUser?.name || githubUser?.login) : 'GitHub Account'}
                    </h3>
                    {connected ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-300 border border-emerald-500/20">
                        <CheckCircle2 className="size-3" /> Connected
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-300 border border-amber-500/20">
                        <AlertCircle className="size-3" /> Not Connected
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {connected
                      ? `@${githubUser?.login} • ${repos.length} total repositories available (public & private)`
                      : 'Connect your GitHub account or provide a Personal Access Token to list your public and private repositories.'}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowTokenInput((v) => !v)}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-medium text-slate-300 hover:bg-white/[0.08] transition-colors"
                >
                  <KeyRound className="size-3.5" />
                  {showTokenInput ? 'Close Token Input' : 'PAT Token / Key'}
                </button>
                <button
                  onClick={() => fetchRepos()}
                  disabled={loading}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-medium text-slate-300 hover:bg-white/[0.08] disabled:opacity-50 transition-colors"
                >
                  <RefreshCw className={`size-3.5 ${loading ? 'animate-spin' : ''}`} />
                  Refresh
                </button>
              </div>
            </div>

            {/* Token Input Dropdown */}
            {showTokenInput && (
              <div className="rounded-2xl border border-white/10 bg-[#11151d] p-5 space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <h4 className="text-sm font-semibold text-white">GitHub Personal Access Token (PAT)</h4>
                    <p className="text-xs text-slate-400 mt-1">
                      If your Clerk account does not have GitHub OAuth linked, enter a token with{' '}
                      <code className="text-cyan-300">repo</code> scope to load both private and public repositories.
                    </p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <input
                    type="password"
                    value={tokenInput}
                    onChange={(e) => setTokenInput(e.target.value)}
                    placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                    className="flex-1 rounded-xl border border-white/10 bg-black/40 px-3.5 py-2 text-xs text-white placeholder-slate-500 outline-none focus:border-cyan-400"
                  />
                  <button
                    onClick={handleSaveToken}
                    className="rounded-xl bg-cyan-300 px-4 py-2 text-xs font-semibold text-slate-950 hover:bg-cyan-200 transition-colors"
                  >
                    Save & Load Repos
                  </button>
                </div>
              </div>
            )}

            {/* Repositories Search and Filter Controls */}
            {connected && (
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                {/* Search Bar */}
                <div className="relative flex-1 max-w-md">
                  <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-slate-500" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search repositories by name or description…"
                    className="w-full rounded-xl border border-white/10 bg-black/30 py-2.5 pl-10 pr-4 text-xs text-white placeholder-slate-500 outline-none focus:border-cyan-300"
                  />
                </div>

                {/* Filters */}
                <div className="flex flex-wrap items-center gap-2">
                  {/* Visibility Filters */}
                  <div className="flex rounded-xl border border-white/10 bg-black/20 p-1">
                    {(['all', 'private', 'public'] as const).map((v) => (
                      <button
                        key={v}
                        onClick={() => setVisibilityFilter(v)}
                        className={`rounded-lg px-2.5 py-1 text-xs font-medium capitalize transition-colors ${
                          visibilityFilter === v
                            ? 'bg-cyan-300 text-slate-950 font-semibold'
                            : 'text-slate-400 hover:text-white'
                        }`}
                      >
                        {v === 'private' ? '🔒 Private' : v === 'public' ? '🌐 Public' : 'All'}
                      </button>
                    ))}
                  </div>

                  {/* Language Filter */}
                  {availableLanguages.length > 0 && (
                    <select
                      value={selectedLanguage}
                      onChange={(e) => setSelectedLanguage(e.target.value)}
                      aria-label="Filter repositories by programming language"
                      className="rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-xs text-white outline-none focus:border-cyan-300"
                    >
                      <option value="all">All Languages</option>
                      {availableLanguages.map((lang) => (
                        <option key={lang} value={lang}>
                          {lang}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              </div>
            )}

            {/* Repositories Grid */}
            {loading ? (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {[...Array(6)].map((_, i) => (
                  <div key={i} className="h-44 rounded-2xl border border-white/[0.06] bg-white/[0.02] p-5 animate-pulse space-y-3">
                    <div className="h-5 w-3/4 rounded bg-white/10" />
                    <div className="h-4 w-full rounded bg-white/5" />
                    <div className="h-4 w-1/2 rounded bg-white/5" />
                    <div className="mt-4 h-9 w-full rounded-xl bg-white/10" />
                  </div>
                ))}
              </div>
            ) : filteredRepos.length > 0 ? (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {filteredRepos.map((repo) => (
                  <div
                    key={repo.id}
                    className="flex flex-col justify-between rounded-2xl border border-white/[0.08] bg-white/[0.035] p-5 transition-all hover:border-cyan-300/40 hover:bg-white/[0.05]"
                  >
                    <div>
                      {/* Card Header */}
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2 overflow-hidden">
                          {repo.private ? (
                            <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-amber-400/10 text-amber-300" title="Private Repository">
                              <Lock className="size-3.5" />
                            </span>
                          ) : (
                            <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-slate-400/10 text-slate-300" title="Public Repository">
                              <Globe className="size-3.5" />
                            </span>
                          )}
                          <h4 className="font-semibold text-white text-sm truncate" title={repo.name}>
                            {repo.name}
                          </h4>
                        </div>
                        <a
                          href={repo.html_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="shrink-0 text-slate-500 hover:text-white transition-colors"
                          title="Open on GitHub"
                        >
                          <ExternalLink className="size-4" />
                        </a>
                      </div>

                      {/* Description */}
                      <p className="mt-2.5 text-xs text-slate-400 line-clamp-2 min-h-8">
                        {repo.description || 'No description provided.'}
                      </p>

                      {/* Meta Tags */}
                      <div className="mt-4 flex flex-wrap items-center gap-3 text-[11px] text-slate-400">
                        {repo.language && (
                          <span className="flex items-center gap-1.5 font-medium text-slate-300">
                            <span
                              className="size-2 rounded-full"
                              style={{ backgroundColor: LANGUAGE_COLORS[repo.language] || '#94a3b8' }}
                            />
                            {repo.language}
                          </span>
                        )}
                        {repo.stargazers_count > 0 && (
                          <span className="flex items-center gap-1">
                            <Star className="size-3 text-amber-300" />
                            {repo.stargazers_count}
                          </span>
                        )}
                        <span className="flex items-center gap-1">
                          <GitBranch className="size-3 text-slate-500" />
                          {repo.default_branch}
                        </span>
                      </div>
                    </div>

                    {/* Action Button */}
                    <div className="mt-5 pt-3 border-t border-white/[0.06]">
                      <button
                        onClick={() => handleImportRepo(repo)}
                        disabled={importingRepoId === repo.id}
                        className="w-full flex items-center justify-center gap-2 rounded-xl bg-cyan-300 px-3.5 py-2 text-xs font-semibold text-slate-950 transition-colors hover:bg-cyan-200 disabled:opacity-50"
                      >
                        {importingRepoId === repo.id ? (
                          <>
                            <RefreshCw className="size-3.5 animate-spin" />
                            Importing…
                          </>
                        ) : (
                          <>
                            <Plus className="size-3.5" />
                            Import Project
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : connected ? (
              <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] p-12 text-center">
                <Search className="size-8 mx-auto text-slate-600 mb-3" />
                <h4 className="text-sm font-semibold text-white">No matching repositories found</h4>
                <p className="text-xs text-slate-400 mt-1">
                  Try adjusting your search query or filter settings.
                </p>
              </div>
            ) : (
              <div className="rounded-2xl border border-white/[0.08] bg-white/[0.035] p-12 text-center space-y-4">
                <div className="size-14 mx-auto rounded-2xl bg-cyan-300/10 flex items-center justify-center text-cyan-300">
                  <FolderGit2 className="size-7" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-white">Connect Your GitHub Account</h3>
                  <p className="text-xs text-slate-400 max-w-md mx-auto mt-1">
                    Connect your GitHub account to instantly browse, view details, and import all your public and private repositories.
                  </p>
                </div>
                <div className="pt-2 flex flex-wrap justify-center gap-3">
                  <button
                    onClick={() => setShowTokenInput(true)}
                    className="rounded-xl bg-cyan-300 px-5 py-2.5 text-xs font-semibold text-slate-950 hover:bg-cyan-200 transition-colors"
                  >
                    Enter GitHub Token (PAT)
                  </button>
                  <button
                    onClick={() => setActiveTab('manual')}
                    className="rounded-xl border border-white/10 px-5 py-2.5 text-xs font-semibold text-slate-300 hover:bg-white/[0.05] transition-colors"
                  >
                    Use Custom Repository URL
                  </button>
                </div>
              </div>
            )}
          </div>
        ) : (
          /* Manual / Custom Git URL */
          <div className="max-w-xl rounded-2xl border border-white/[0.08] bg-white/[0.035] p-6 space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-white">Custom Git Repository</h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Manually enter a project name and repository clone URL.
              </p>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400">Project name</label>
              <input
                value={manualName}
                onChange={(e) => setManualName(e.target.value)}
                placeholder="My Java Service"
                className="mt-1.5 w-full rounded-xl border border-white/10 bg-black/30 px-3.5 py-2.5 text-xs text-white placeholder-slate-500 outline-none focus:border-cyan-300"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400">Repository URL</label>
              <input
                value={manualUrl}
                onChange={(e) => setManualUrl(e.target.value)}
                placeholder="https://github.com/organization/repository"
                className="mt-1.5 w-full rounded-xl border border-white/10 bg-black/30 px-3.5 py-2.5 text-xs text-white placeholder-slate-500 outline-none focus:border-cyan-300"
              />
            </div>

            {manualError && <p className="text-xs text-red-300">{manualError}</p>}

            <div className="pt-2">
              <button
                onClick={handleManualSubmit}
                disabled={!manualName.trim()}
                className="rounded-xl bg-cyan-300 px-5 py-2.5 text-xs font-semibold text-slate-950 transition-colors hover:bg-cyan-200 disabled:opacity-40"
              >
                Create Project & Verify
              </button>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  )
}
