import test from 'node:test'
import assert from 'node:assert/strict'
import { authenticatedFetch, getActiveToken } from '../../lib/api/client.ts'
import { isolatedPreviewUrl } from '../../lib/preview.ts'

test('401 refreshes Clerk once and replays a POST body', async () => {
  const oldWindow = globalThis.window
  const oldFetch = globalThis.fetch
  const calls = []
  globalThis.window = { Clerk: { session: { getToken: async options => options.skipCache ? 'fresh-token' : 'expired-token' } } }
  globalThis.fetch = async (request, options) => {
    calls.push({ token: new Headers(options.headers).get('Authorization'), body: await request.text() })
    return new Response('{}', { status: calls.length === 1 ? 401 : 200 })
  }
  try {
    const response = await authenticatedFetch(new Request('http://api.example/projects', { method: 'POST', body: '{"name":"demo"}' }))
    assert.equal(response.status, 200)
    assert.deepEqual(calls, [{ token: 'Bearer expired-token', body: '{"name":"demo"}' }, { token: 'Bearer fresh-token', body: '{"name":"demo"}' }])
  } finally { globalThis.window = oldWindow; globalThis.fetch = oldFetch }
})

test('a signed-out Clerk session never falls back to stale local JWT', async () => {
  const previous = globalThis.window
  globalThis.window = { Clerk: {}, localStorage: { getItem: () => 'stale-local-token' } }
  try { assert.equal(await getActiveToken(), null) } finally { globalThis.window = previous }
})

test('persistent unauthorized responses stop after one retry', async () => {
  const previous = globalThis.window
  const oldFetch = globalThis.fetch
  let requests = 0
  const events = []
  globalThis.window = { Clerk: { session: { getToken: async () => 'invalid' } }, localStorage: { removeItem: () => {} }, dispatchEvent: event => events.push(event.type) }
  globalThis.fetch = async () => { requests++; return new Response('{}', { status: 401 }) }
  try {
    assert.equal((await authenticatedFetch('http://api.example/projects')).status, 401)
    assert.equal(requests, 2)
    assert.deepEqual(events, ['migrationguard:unauthorized'])
  } finally { globalThis.window = previous; globalThis.fetch = oldFetch }
})

test('loopback preview uses a different cookie host', () => {
  assert.equal(isolatedPreviewUrl('http://127.0.0.1:8080', 'http://127.0.0.1:3001'), 'http://localhost:8080/')
  assert.equal(isolatedPreviewUrl('http://localhost:8080', 'http://localhost:3001'), 'http://127.0.0.1:8080/')
  assert.equal(isolatedPreviewUrl('https://app.example.com:8080', 'https://app.example.com'), null)
  assert.equal(isolatedPreviewUrl('javascript:alert(1)', 'https://app.example.com'), null)
  assert.equal(isolatedPreviewUrl('https://preview.example.net', 'https://app.example.com'), 'https://preview.example.net/')
})
