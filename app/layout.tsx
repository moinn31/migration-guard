import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'
import './globals.css'
import { Providers } from './providers'

export const metadata: Metadata = {
  title: 'MigrationGuard — Don’t just migrate. Verify.',
  description: 'Independent evidence for safer Java migrations.',
  generator: 'v0.app',
  icons: { icon: '/icon.svg', apple: '/apple-icon.png' },
}

export const viewport: Viewport = {
  colorScheme: 'dark light',
  themeColor: '#080a0f',
  userScalable: false,
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" className="dark"><body className="antialiased"><Providers>{children}</Providers>{process.env.NODE_ENV === 'production' && <Analytics />}</body></html>
}
