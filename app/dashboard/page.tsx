'use client'

import dynamic from 'next/dynamic'

const DashboardView = dynamic(() => import('./dashboard-view'), { ssr: false })

export default function DashboardPage() {
  return <DashboardView />
}
