/** Keep repository JavaScript on a different cookie host from the workspace. */
export function isolatedPreviewUrl(configured: string | null | undefined, workspaceOrigin: string): string | null {
  if (!configured) return null
  try {
    const preview = new URL(configured)
    const workspace = new URL(workspaceOrigin)
    if (!['http:', 'https:'].includes(preview.protocol) || preview.username || preview.password) return null
    if (preview.hostname === workspace.hostname) {
      if (preview.hostname === '127.0.0.1') preview.hostname = 'localhost'
      else if (preview.hostname === 'localhost') preview.hostname = '127.0.0.1'
      else return null
    }
    return preview.toString()
  } catch { return null }
}
