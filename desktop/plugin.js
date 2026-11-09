// Sightline — Hermes Desktop pane: makes the Solana transaction firewall visible.
//
// Desktop half of the Sightline unified package. Plain ESM, loaded uncompiled by the
// Desktop plugin SDK; imports only @hermes/plugin-sdk, react and react/jsx-runtime.
//
// Data comes from this package's own backend (dashboard/plugin_api.py) via ctx.rest:
//   GET  /state           read-only snapshot
//   POST /revoke {id}     revoke one grant (narrows permissions only)
// There is no way to create or widen a grant from here: that stays /sightline grant.
//
// Live updates: the Python side emits `plugin.sightline.audit` after every committed
// audit write (decision, send, grant created/revoked); the pane re-reads /state.

import {
  Badge, Button, CopyButton, EmptyState, PALETTE_AREA, PANES_AREA, STATUSBAR_AREAS,
  host, queryClient, relativeTime, useMutation, useQuery
} from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'sightline'
const PANE_ID = `${ID}:pane`
const STATE_KEY = [ID, 'state']
const AUDIT_EVENT = `plugin.${ID}.audit`
const POLL_MS = 5000 // only when the event stream is unavailable
const SAFETY_MS = 15000 // activity from other processes (CLI, cron) never reaches this window as an event

// Disk plugins are not scanned by Tailwind, so layout lives here. Colors come only
// from the app's theme variables, so light/dark and custom themes just work.
const CSS = `
.sl-pane{display:flex;flex-direction:column;height:100%;min-height:0;font-size:12px;color:var(--ui-text-secondary)}
.sl-scroll{flex:1;min-height:0;overflow-y:auto;padding:10px 12px 16px;display:flex;flex-direction:column;gap:14px}
.sl-header{display:flex;flex-direction:column;gap:6px;padding-bottom:10px;border-bottom:1px solid var(--ui-stroke-secondary)}
.sl-row{display:flex;align-items:center;gap:6px;min-width:0}
.sl-title{font-size:13px;font-weight:600;color:var(--ui-text-primary)}
.sl-key{font-family:var(--font-mono,monospace);color:var(--ui-text-secondary)}
.sl-balances{display:flex;flex-wrap:wrap;gap:4px 12px;font-variant-numeric:tabular-nums}
.sl-balance b{font-weight:600;color:var(--ui-text-primary)}
.sl-muted{color:var(--ui-text-tertiary)}
.sl-faint{color:var(--ui-text-quaternary)}
.sl-section-title{font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--ui-text-tertiary);margin-bottom:6px}
.sl-cards{display:flex;flex-direction:column;gap:8px}
.sl-card{border:1px solid var(--ui-stroke-secondary);border-radius:6px;padding:8px 10px;display:flex;flex-direction:column;gap:5px}
.sl-card[data-status=revoked],.sl-card[data-status=expired]{opacity:.55}
.sl-spread{display:flex;align-items:center;justify-content:space-between;gap:8px;min-width:0}
.sl-bar{height:4px;border-radius:2px;background:var(--ui-stroke-secondary);overflow:hidden}
.sl-bar>span{display:block;height:100%;background:var(--ui-accent);transition:width .3s}
.sl-bar[data-full=true]>span{background:var(--ui-text-tertiary)}
.sl-feed{display:flex;flex-direction:column}
.sl-item{display:flex;flex-direction:column;gap:3px;padding:7px 0;border-bottom:1px solid var(--ui-stroke-secondary)}
.sl-item:last-child{border-bottom:0}
.sl-explain{white-space:pre-wrap;color:var(--ui-text-primary);line-height:1.45}
.sl-link{background:none;border:0;padding:0;font:inherit;color:var(--ui-accent);cursor:pointer;text-align:left}
.sl-link:hover{text-decoration:underline}
.sl-error{color:var(--ui-text-tertiary);font-style:italic}
.sl-status{display:flex;align-items:center;gap:4px;height:100%;padding:0 6px;font-size:.6875rem;color:var(--ui-text-tertiary);background:none;border:0;cursor:pointer}
.sl-status:hover{color:var(--ui-text-secondary)}
`

const VERDICT_VARIANT = { ALLOW: 'success', APPROVE: 'warn', BLOCK: 'destructive' }

function short(addr) {
  if (!addr) return '?'
  if (addr === '*') return 'any recipient'
  return addr.length > 12 ? `${addr.slice(0, 4)}…${addr.slice(-4)}` : addr
}

function left(seconds) {
  const s = Math.max(0, Math.floor(seconds))
  if (s >= 86400) return `${Math.floor(s / 86400)}d ${Math.floor((s % 86400) / 3600)}h`
  if (s >= 3600) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
  if (s >= 60) return `${Math.floor(s / 60)}m ${s % 60}s`
  return `${s}s`
}

function useNow(ms = 1000) {
  const [now, setNow] = useState(() => Date.now() / 1000)
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now() / 1000), ms)
    return () => clearInterval(t)
  }, [ms])
  return now
}

function makeStateQuery(ctx, live) {
  return {
    queryKey: STATE_KEY,
    queryFn: () => ctx.rest('/state'),
    refetchInterval: live ? SAFETY_MS : POLL_MS,
    refetchOnWindowFocus: true,
    retry: 1
  }
}

// ── header ──────────────────────────────────────────────────────────────────

function Header({ state }) {
  const mainnet = state.network === 'mainnet'
  const b = state.balances
  return jsxs('div', { className: 'sl-header', children: [
    jsxs('div', { className: 'sl-spread', children: [
      jsx('span', { className: 'sl-title', children: 'Sightline firewall' }),
      jsx(Badge, { variant: mainnet ? 'destructive' : 'muted', children: (state.network || '?').toUpperCase() })
    ] }),
    state.pubkey
      ? jsxs('div', { className: 'sl-row', children: [
          jsx('span', { className: 'sl-key', title: state.pubkey, children: short(state.pubkey) }),
          jsx(CopyButton, { text: state.pubkey, label: 'Copy wallet address', buttonSize: 'icon-xs' })
        ] })
      : jsx('span', { className: 'sl-error', children: 'No wallet configured (set SIGHTLINE_SECRET_KEY)' }),
    b
      ? jsxs('div', { className: 'sl-balances', children: [
          jsxs('span', { className: 'sl-balance', children: [jsx('b', { children: b.sol }), ' SOL'] }),
          ...b.tokens.map(t => jsxs('span', { className: 'sl-balance', title: t.mint, children: [
            jsx('b', { children: t.amount }), ` ${t.symbol}`
          ] }, t.mint))
        ] })
      : state.wallet_error && state.pubkey && jsx('span', { className: 'sl-error', children: `Balances unavailable: ${state.wallet_error.message}` })
  ] })
}

// ── grants ──────────────────────────────────────────────────────────────────

function GrantCard({ grant, ctx, now }) {
  const revoke = useMutation({
    mutationFn: () => ctx.rest('/revoke', { method: 'POST', body: { id: grant.id } }),
    onSuccess: () => {
      host.notify({ kind: 'info', message: `Revoked ${grant.id}` })
      queryClient.invalidateQueries({ queryKey: STATE_KEY })
    },
    onError: err => host.notify({ kind: 'error', message: `Revoke failed: ${err?.message || err}` })
  })
  const active = grant.status === 'active'
  const cap = Number(grant.daily_cap)
  const used = Number(grant.used_24h || 0)
  const pct = cap > 0 ? Math.min(100, (used / cap) * 100) : 0
  const recipients = grant.recipients.map(short).join(', ')
  return jsxs('div', { className: 'sl-card', 'data-status': grant.status, children: [
    jsxs('div', { className: 'sl-spread', children: [
      jsxs('span', { className: 'sl-row', children: [
        jsx('b', { className: 'sl-title', children: grant.symbol }),
        jsx('span', { className: 'sl-faint sl-key', children: grant.id })
      ] }),
      active
        ? jsx(Button, { size: 'xs', variant: 'outline', disabled: revoke.isPending, onClick: () => revoke.mutate(),
            children: revoke.isPending ? 'Revoking…' : 'Revoke' })
        : jsx(Badge, { variant: 'muted', children: grant.status })
    ] }),
    active && jsxs('div', { className: 'sl-spread', children: [
      jsxs('span', { children: [`${grant.used_24h} / ${grant.daily_cap} ${grant.symbol}`, jsx('span', { className: 'sl-muted', children: ' used (24h)' })] }),
      jsx('span', { className: 'sl-muted', children: `max ${grant.max_per_tx}/tx` })
    ] }),
    active && jsx('div', { className: 'sl-bar', 'data-full': pct >= 100, children: jsx('span', { style: { width: `${pct}%` } }) }),
    jsxs('div', { className: 'sl-spread', children: [
      jsx('span', { className: 'sl-muted', title: grant.recipients.join('\n'), children: `to ${recipients}` }),
      jsx('span', { className: 'sl-muted', children: active ? `${left(grant.expires_at - now)} left` : '' })
    ] }),
    grant.note && jsx('span', { className: 'sl-faint', children: `“${grant.note}”` })
  ] })
}

function Grants({ grants, ctx }) {
  const now = useNow()
  const active = grants.filter(g => g.status === 'active' && g.expires_at > now)
  const ended = grants.filter(g => !active.includes(g))
  return jsxs('section', { children: [
    jsx('div', { className: 'sl-section-title', children: `Active grants (${active.length})` }),
    active.length === 0
      ? jsx(EmptyState, { className: 'min-h-0 py-4', title: 'No active grants',
          description: 'Every payment needs your approval. Create one with /sightline grant <cap> <token> to <addr> for 1h' })
      : jsx('div', { className: 'sl-cards', children: active.map(g => jsx(GrantCard, { grant: g, ctx, now }, g.id)) }),
    ended.length > 0 && jsx('div', { className: 'sl-cards', style: { marginTop: 8 },
      children: ended.map(g => jsx(GrantCard, { grant: { ...g, status: g.status === 'active' ? 'expired' : g.status }, ctx, now }, g.id)) })
  ] })
}

// ── activity ────────────────────────────────────────────────────────────────

function amountLine(e) {
  return e.amount ? `${e.amount} ${e.symbol || ''} → ${short(e.recipient)}` : ''
}

function ActivityItem({ e, ctx }) {
  const when = jsx('span', { className: 'sl-faint', title: new Date(e.ts * 1000).toLocaleString(),
    children: relativeTime(e.ts * 1000) })
  if (e.event === 'decision') {
    return jsxs('div', { className: 'sl-item', children: [
      jsxs('div', { className: 'sl-spread', children: [
        jsxs('span', { className: 'sl-row', children: [
          jsx(Badge, { variant: VERDICT_VARIANT[e.verdict] || 'muted', children: e.verdict }),
          jsx('span', { children: amountLine(e) })
        ] }),
        when
      ] }),
      e.explanation && jsx('div', { className: 'sl-explain', children: e.explanation }),
      jsx('div', { className: 'sl-muted', children: `${e.reason || ''}${e.rule ? ` · rule: ${e.rule}` : ''}${e.source === 'execute' ? ' · second gate' : ''}` })
    ] })
  }
  if (e.event === 'sent') {
    return jsxs('div', { className: 'sl-item', children: [
      jsxs('div', { className: 'sl-spread', children: [
        jsxs('span', { className: 'sl-row', children: [jsx(Badge, { variant: 'success', children: 'SENT' }),
          jsx('span', { className: 'sl-key', children: short(e.signature) })] }),
        when
      ] }),
      e.explorer_url && jsx('button', { type: 'button', className: 'sl-link',
        onClick: () => void ctx.os.openExternal(e.explorer_url), children: 'View on Solana Explorer ↗' })
    ] })
  }
  const label = {
    execute: ['SIGNING', 'muted', `${amountLine(e)} via ${e.approval}${e.grant_id ? ` ${e.grant_id}` : ''}`],
    failed: ['FAILED', 'destructive', `${e.error || ''} ${e.message || ''}`],
    grant_created: ['GRANT', 'default', `${e.grant_id} created: ${e.daily_cap} ${e.symbol}/24h`],
    grant_revoked: ['REVOKED', 'muted', `${e.grant_id} revoked`]
  }[e.event] || [e.event.toUpperCase(), 'muted', '']
  return jsx('div', { className: 'sl-item', children: jsxs('div', { className: 'sl-spread', children: [
    jsxs('span', { className: 'sl-row', children: [jsx(Badge, { variant: label[1], children: label[0] }), jsx('span', { children: label[2] })] }),
    when
  ] }) })
}

function Activity({ items, ctx, state }) {
  return jsxs('section', { children: [
    jsxs('div', { className: 'sl-spread', children: [
      jsx('div', { className: 'sl-section-title', children: 'Activity' }),
      jsx('span', { className: 'sl-faint', title: state.audit_status, children: state.audit_ok ? 'log verified ✓' : 'log chain BROKEN ✗' })
    ] }),
    items.length === 0
      ? jsx(EmptyState, { className: 'min-h-0 py-4', title: 'No activity yet',
          description: 'Firewall decisions and payments appear here as they happen.' })
      : jsx('div', { className: 'sl-feed', children: items.map(e => jsx(ActivityItem, { e, ctx }, e.seq)) })
  ] })
}

// ── pane + status bar ───────────────────────────────────────────────────────

function Pane({ ctx, live }) {
  const q = useQuery(makeStateQuery(ctx, live))
  if (q.isLoading) return jsx('div', { className: 'sl-pane', children: jsx('div', { className: 'sl-scroll sl-muted', children: 'Loading…' }) })
  if (q.error || !q.data) {
    return jsx('div', { className: 'sl-pane', children: jsx('div', { className: 'sl-scroll', children: jsx(EmptyState, {
      title: 'Sightline backend unavailable',
      description: 'Enable the sightline plugin (plugins.enabled in config.yaml) and restart the gateway.'
    }) }) })
  }
  const state = q.data
  return jsx('div', { className: 'sl-pane', children: jsxs('div', { className: 'sl-scroll', children: [
    jsx(Header, { state }),
    jsx(Grants, { grants: state.grants, ctx }),
    jsx(Activity, { items: state.recent_audit, ctx, state })
  ] }) })
}

function StatusItem({ ctx, live }) {
  const { data } = useQuery(makeStateQuery(ctx, live))
  const now = Date.now() / 1000
  const n = data ? data.grants.filter(g => g.status === 'active' && g.expires_at > now).length : 0
  const last = data && data.recent_audit.find(e => e.event === 'decision')
  const text = data ? `Sightline • ${n} grant${n === 1 ? '' : 's'}${last ? ` • last: ${last.verdict}` : ''}` : 'Sightline'
  return jsx('button', { type: 'button', className: 'sl-status', title: 'Open Sightline firewall',
    onClick: () => host.revealPane(PANE_ID), children: text })
}

export default {
  id: ID,
  name: 'Sightline',
  description: 'Solana transaction firewall: wallet, active grants and a live decision feed.',
  register(ctx) {
    const style = document.createElement('style')
    style.textContent = CSS
    document.head.append(style)
    ctx.onDispose(() => style.remove())

    const live = typeof ctx.onEvent === 'function'
    if (live) ctx.onEvent(AUDIT_EVENT, () => queryClient.invalidateQueries({ queryKey: STATE_KEY }))

    ctx.registerMany([
      { id: 'pane', area: PANES_AREA, title: 'Sightline',
        data: { placement: 'right', width: '340px' }, render: () => jsx(Pane, { ctx, live }) },
      { id: 'open', area: PALETTE_AREA,
        data: { id: 'sightline.open', label: 'Sightline: Open firewall', keywords: ['sightline', 'solana', 'firewall', 'grants', 'wallet'],
          run: () => host.revealPane(PANE_ID) } },
      { id: 'status', area: STATUSBAR_AREAS.right, order: 140, render: () => jsx(StatusItem, { ctx, live }) }
    ])
  }
}
