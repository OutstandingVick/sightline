// Loads desktop/plugin.js against a stub SDK and checks what it registers.
// Run: node --test tests/js/*.test.mjs
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'

const ROOT = fileURLToPath(new URL('../../', import.meta.url))
const SOURCE = readFileSync(join(ROOT, 'desktop/plugin.js'), 'utf8')

const SDK_STUB = `
export const PANES_AREA = 'panes', PALETTE_AREA = 'palette'
export const STATUSBAR_AREAS = { left: 'statusBar.left', right: 'statusBar.right' }
export const host = { revealed: [], revealPane(id) { this.revealed.push(id) }, notify() {} }
export const queryClient = { invalidated: [], invalidateQueries(q) { this.invalidated.push(q) } }
const C = () => null
export const Badge = C, Button = C, CopyButton = C, EmptyState = C
export const relativeTime = () => 'now', useMutation = () => ({}), useQuery = () => ({})
`
const REACT_STUB = 'export const useEffect = () => {}, useState = v => [v, () => {}]'
const JSX_STUB = 'export const jsx = (t, p) => ({ t, p }), jsxs = (t, p) => ({ t, p })'

async function load() {
  const dir = mkdtempSync(join(tmpdir(), 'sightline-js-'))
  for (const [name, body] of [['sdk.mjs', SDK_STUB], ['react.mjs', REACT_STUB], ['jsx.mjs', JSX_STUB]]) {
    writeFileSync(join(dir, name), body)
  }
  const src = SOURCE
    .replace("from '@hermes/plugin-sdk'", `from '${pathToFileURL(join(dir, 'sdk.mjs'))}'`)
    .replace("from 'react/jsx-runtime'", `from '${pathToFileURL(join(dir, 'jsx.mjs'))}'`)
    .replace("from 'react'", `from '${pathToFileURL(join(dir, 'react.mjs'))}'`)
  writeFileSync(join(dir, 'plugin.mjs'), src)
  globalThis.document = { createElement: () => ({}), head: { append() {} } }
  const plugin = (await import(pathToFileURL(join(dir, 'plugin.mjs')))).default
  const sdk = await import(pathToFileURL(join(dir, 'sdk.mjs')))
  return { plugin, sdk }
}

function fakeCtx() {
  const ctx = { contributions: [], events: {}, disposers: [] }
  ctx.registerMany = cs => { ctx.contributions.push(...cs); return () => {} }
  ctx.register = c => { ctx.contributions.push(c); return () => {} }
  ctx.onEvent = (type, fn) => { ctx.events[type] = fn; return () => {} }
  ctx.onDispose = fn => ctx.disposers.push(fn)
  ctx.rest = async () => ({})
  return ctx
}

test('only imports what the disk loader allows', () => {
  const specifiers = [...SOURCE.matchAll(/from\s+'([^']+)'/g)].map(m => m[1])
  assert.deepEqual([...new Set(specifiers)].sort(), ['@hermes/plugin-sdk', 'react', 'react/jsx-runtime'])
  assert.doesNotMatch(SOURCE, /\bimport\(|\beval\(|new Function|<script|data-slot|data-testid|hermesDesktop/)
})

test('registers pane, palette entry and status bar item', async () => {
  const { plugin } = await load()
  const ctx = fakeCtx()
  assert.equal(plugin.id, 'sightline')
  plugin.register(ctx)
  const byArea = Object.fromEntries(ctx.contributions.map(c => [c.area, c]))
  assert.equal(byArea.panes.title, 'Sightline')
  assert.equal(byArea.palette.data.label, 'Sightline: Open firewall')
  assert.ok(byArea['statusBar.right'].render)
})

test('palette entry reveals the pane', async () => {
  const { plugin, sdk } = await load()
  const ctx = fakeCtx()
  plugin.register(ctx)
  ctx.contributions.find(c => c.area === 'palette').data.run()
  assert.deepEqual(sdk.host.revealed, ['sightline:pane'])
})

test('audit event refreshes state', async () => {
  const { plugin, sdk } = await load()
  const ctx = fakeCtx()
  plugin.register(ctx)
  ctx.events['plugin.sightline.audit']({ payload: {} })
  assert.deepEqual(sdk.queryClient.invalidated.at(-1), { queryKey: ['sightline', 'state'] })
})

test('the pane only ever POSTs to /revoke', () => {
  const posts = [...SOURCE.matchAll(/ctx\.rest\('([^']+)',\s*\{\s*method:\s*'POST'/g)].map(m => m[1])
  assert.deepEqual(posts, ['/revoke'])
})

test('styles use theme variables, never hardcoded colors', () => {
  const css = SOURCE.match(/const CSS = `([\s\S]*?)`/)[1]
  assert.doesNotMatch(css, /#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(|oklch\(/i)
  assert.match(css, /var\(--ui-accent\)/)
})

test('the stylesheet is removed on dispose', async () => {
  const { plugin } = await load()
  let removed = false
  globalThis.document = { createElement: () => ({ remove: () => { removed = true } }), head: { append() {} } }
  const ctx = fakeCtx()
  plugin.register(ctx)
  ctx.disposers.forEach(fn => fn())
  assert.ok(removed)
})

test('grant usage label follows the grant period', () => {
  assert.match(SOURCE, /used \(\$\{grant\.period \|\| '24h'\}\)/)
})
