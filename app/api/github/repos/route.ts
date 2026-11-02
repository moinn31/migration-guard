import { auth, clerkClient } from '@clerk/nextjs/server'
import { NextResponse } from 'next/server'

export async function GET(request: Request) {
  try {
    const { userId } = await auth()
    if (!userId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    let githubToken: string | null = null

    // 1. Try to get GitHub OAuth token from Clerk
    try {
      const client = await clerkClient()
      const oauthTokens = await client.users.getUserOauthAccessToken(userId, 'oauth_github')
      if (oauthTokens.data && oauthTokens.data.length > 0) {
        githubToken = oauthTokens.data[0].token
      }
    } catch (err) {
      console.warn('Could not fetch Clerk OAuth token for github:', err)
    }

    // 2. Check request header for user-provided Personal Access Token
    const customToken = request.headers.get('x-github-token')
    if (!githubToken && customToken) {
      githubToken = customToken
    }

    // 3. Check environment variable GITHUB_TOKEN
    if (!githubToken && process.env.GITHUB_TOKEN) {
      githubToken = process.env.GITHUB_TOKEN
    }

    if (!githubToken) {
      return NextResponse.json({
        connected: false,
        message: 'No GitHub account or token connected. Connect your GitHub account via Clerk or provide a GitHub Personal Access Token.',
      })
    }

    // 4. Fetch repositories from GitHub API (both public and private)
    const githubRes = await fetch(
      'https://api.github.com/user/repos?visibility=all&affiliation=owner,collaborator,organization_member&sort=updated&per_page=100',
      {
        headers: {
          Authorization: `Bearer ${githubToken}`,
          Accept: 'application/vnd.github.v3+json',
          'User-Agent': 'MigrationGuard-App',
        },
        cache: 'no-store',
      }
    )

    if (!githubRes.ok) {
      const errorText = await githubRes.text()
      return NextResponse.json(
        { connected: false, message: `GitHub API returned ${githubRes.status}: ${errorText}` },
        { status: 502 }
      )
    }

    const repos = await githubRes.json()

    // 5. Fetch authenticated GitHub user details
    let userProfile = null
    try {
      const userRes = await fetch('https://api.github.com/user', {
        headers: {
          Authorization: `Bearer ${githubToken}`,
          Accept: 'application/vnd.github.v3+json',
          'User-Agent': 'MigrationGuard-App',
        },
      })
      if (userRes.ok) {
        userProfile = await userRes.json()
      }
    } catch {}

    const formattedRepos = repos.map((r: {
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
      owner?: { login: string; avatar_url: string }
    }) => ({
      id: r.id,
      name: r.name,
      full_name: r.full_name,
      private: r.private,
      html_url: r.html_url,
      clone_url: r.clone_url,
      description: r.description,
      language: r.language,
      stargazers_count: r.stargazers_count,
      forks_count: r.forks_count,
      updated_at: r.updated_at,
      default_branch: r.default_branch,
      owner: {
        login: r.owner?.login || '',
        avatar_url: r.owner?.avatar_url || '',
      },
    }))

    return NextResponse.json({
      connected: true,
      user: userProfile
        ? {
            login: userProfile.login,
            name: userProfile.name,
            avatar_url: userProfile.avatar_url,
            html_url: userProfile.html_url,
            public_repos: userProfile.public_repos,
            total_private_repos: userProfile.total_private_repos,
          }
        : null,
      repos: formattedRepos,
    })
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : 'Internal Server Error'
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
