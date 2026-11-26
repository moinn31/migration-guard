'use client'

import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@clerk/nextjs'
import { api, getActiveToken, getToken, setToken } from './client'

export const queryKeys = {
  projects: ['projects'] as const,
  run: (id: string) => ['runs', id] as const,
  details: (id: string) => ['runs', id, 'details'] as const,
  findings: (id: string) => ['runs', id, 'findings'] as const,
  changes: (id: string) => ['runs', id, 'changes'] as const,
  report: (id: string) => ['runs', id, 'report'] as const,
}

export function useIsAuth() {
  const { isSignedIn, isLoaded } = useAuth()
  const local = getToken()
  if (!isLoaded) return false
  return Boolean(isSignedIn || local)
}

export function useProjects() {
  const isAuth = useIsAuth()
  return useQuery({
    queryKey: queryKeys.projects,
    enabled: isAuth,
    queryFn: async () => {
      const { data, error } = await api.GET('/projects')
      if (error) throw new Error('Unable to load projects')
      return data
    },
  })
}

export function useRun(id: string) {
  const isAuth = useIsAuth()
  return useQuery({
    queryKey: queryKeys.run(id),
    refetchInterval: query => ['ACCEPTED', 'REJECTED', 'AWAITING_APPROVAL', 'INCONCLUSIVE', 'FAILED', 'COMPLETED'].includes(query.state.data?.state ?? '') ? false : 3000,
    enabled: Boolean(id && isAuth),
    queryFn: async () => {
      const { data, error } = await api.GET('/runs/{run_id}', { params: { path: { run_id: id } } })
      if (error) throw new Error('Unable to load run')
      return data
    },
  })
}

export function useRunDetails(id: string) {
  const isAuth = useIsAuth()
  return useQuery({
    queryKey: queryKeys.details(id),
    enabled: Boolean(id && isAuth),
    queryFn: async () => {
      const { data, error } = await api.GET('/runs/{run_id}/details', { params: { path: { run_id: id } } })
      if (error) throw new Error('Unable to load run details')
      return data
    },
  })
}

export function useFindings(id: string) {
  const isAuth = useIsAuth()
  return useQuery({
    queryKey: queryKeys.findings(id),
    enabled: Boolean(id && isAuth),
    queryFn: async () => {
      const { data, error } = await api.GET('/runs/{run_id}/findings', { params: { path: { run_id: id } } })
      if (error) throw new Error('Unable to load findings')
      return data
    },
  })
}

export function useChanges(id: string) {
  const isAuth = useIsAuth()
  return useQuery({
    queryKey: queryKeys.changes(id),
    enabled: Boolean(id && isAuth),
    queryFn: async () => {
      const { data, error } = await api.GET('/runs/{run_id}/changes', { params: { path: { run_id: id } } })
      if (error) throw new Error('Unable to load migration changes')
      return data
    },
  })
}

export function useReport(id: string) {
  const isAuth = useIsAuth()
  const run = useRun(id)
  return useQuery({
    queryKey: queryKeys.report(id),
    refetchInterval: ['ACCEPTED', 'REJECTED', 'AWAITING_APPROVAL', 'INCONCLUSIVE', 'FAILED', 'COMPLETED'].includes(run.data?.state ?? '') ? false : 3000,
    enabled: Boolean(id && isAuth),
    queryFn: async () => {
      const { data, error } = await api.GET('/runs/{run_id}/report', { params: { path: { run_id: id } } })
      if (error) throw new Error('Unable to load report')
      return data
    },
  })
}

export function useCreateRun(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST('/projects/{project_id}/runs', { params: { path: { project_id: projectId } } })
      if (error) throw new Error('Unable to create run')
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.projects }),
  })
}

export function useChangeAction(runId: string, changeId: string, action: 'apply' | 'revert') {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const path = action === 'apply' ? '/runs/{run_id}/changes/{change_id}/apply' : '/runs/{run_id}/changes/{change_id}/revert'
      const { data, error } = await api.POST(path, { params: { path: { run_id: runId, change_id: changeId } } })
      if (error) throw new Error(`Unable to ${action} change`)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.changes(runId) }),
  })
}

export function useApproval(runId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: { decision: string; justification?: string; override_reason?: string }) => {
      const { data, error } = await api.POST('/runs/{run_id}/approval', { params: { path: { run_id: runId } }, body })
      if (error) throw new Error('Unable to save approval')
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.run(runId) }),
  })
}

export function useAiAction(runId: string, action: 'explain' | 'suggest-fix' | 'summary') {
  return useMutation({
    mutationFn: async () => {
      const path = `/runs/{run_id}/ai/${action}` as '/runs/{run_id}/ai/explain' | '/runs/{run_id}/ai/suggest-fix' | '/runs/{run_id}/ai/summary'
      const { data, error } = await api.POST(path, { params: { path: { run_id: runId } } })
      if (error) throw new Error('AI assistance is unavailable')
      return data
    },
  })
}

export function useRunEvents(runId: string) {
  const [event, setEvent] = useState<Record<string, unknown> | null>(null)
  const [connected, setConnected] = useState(false)
  const retry = useRef(0)
  const isAuth = useIsAuth()

  useEffect(() => {
    if (!runId || !isAuth) return
    let source: EventSource | null = null
    let timer: number | undefined
    const connect = async () => {
      const token = await getActiveToken()
      if (!token) return
      source = new EventSource(`${process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000'}/runs/${runId}/events?token=${encodeURIComponent(token)}`)
      source.onopen = () => { setConnected(true); retry.current = 0 }
      source.onmessage = (message) => setEvent(JSON.parse(message.data) as Record<string, unknown>)
      source.onerror = () => {
        setConnected(false)
        source?.close()
        timer = window.setTimeout(connect, Math.min(1000 * 2 ** retry.current++, 15000))
      }
    }
    connect()
    return () => { source?.close(); if (timer) window.clearTimeout(timer) }
  }, [runId, isAuth])
  return { event, connected }
}

export function useAuthRedirect() {
  useEffect(() => {
    const handler = () => {
      setToken(null)
      window.location.href = '/'
    }
    window.addEventListener('migrationguard:unauthorized', handler)
    return () => window.removeEventListener('migrationguard:unauthorized', handler)
  }, [])
}
