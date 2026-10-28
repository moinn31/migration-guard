'use client'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import { useAuthRedirect } from '@/lib/api/hooks'

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 5000, retry: 1 } } }))
  useAuthRedirect()
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}
