# Desktop pane

Sightline ships a Hermes Desktop pane as the desktop half of the same package
(`desktop/plugin.js`), backed by its own routes (`dashboard/plugin_api.py`).

## What it shows

- **Header** — network badge (DEVNET muted, MAINNET red), shortened wallet address
  with a copy button, SOL and token balances.
- **Active grants** — token, used / daily cap with a progress bar, max per tx,
  recipients, a live countdown, and **Revoke**. Revoked/expired grants stay
  visible (dimmed) for 24h.
- **Activity** — the audit log, newest first: verdict chip (ALLOW green / APPROVE
  amber / BLOCK red), the plain-English explanation, reason and rule, amount, time;
  sends link to Solana Explorer. Hook decisions and second-gate decisions both show.
- **Status bar** — `Sightline • N grants • last: BLOCK`; click to open the pane.
- **⌘K** — `Sightline: Open firewall`.

## Backend

| Route | Does |
|---|---|
| `GET /api/plugins/sightline/state` | `{network, pubkey, balances, wallet_error, grants, recent_audit (50, newest first), audit_ok, audit_status, now}` |
| `POST /api/plugins/sightline/revoke {"id"}` | revokes one active grant; writes a `grant_revoked` audit row |

Nothing else. There is no route that creates, widens or extends a grant —
`/sightline grant` (typed by the human) stays the only way in. Revoke is allowed
from the UI because it can only narrow what the agent may do. Responses contain
public data only; `tests/test_plugin_api.py` checks the secret key never appears.

## Live updates

After any transaction that wrote audit rows commits (decision, send, grant
created/revoked), Sightline calls Hermes' `broadcast_plugin_event("sightline",
"audit")`. The pane listens for `plugin.sightline.audit` and re-reads `/state`.
Rolled-back writes emit nothing.

In practice the event rarely arrives. With `plugins.isolation: host` (the default
here) Sightline's commands, tools and hooks run in the plugin-host child process,
and that process has no relay for `broadcast_plugin_event`, so the call is dropped.
Activity from another process (a CLI `hermes chat`, cron) never reaches the window
either. The pane therefore also re-reads `/state` every 5 s. Measured: a grant made
with the slash command appeared in the pane 1.9–6.4 s later.

## Enabling

1. The agent half must be in `plugins.enabled` (it already is if Sightline runs).
   The backend routes mount when the gateway starts.
2. Desktop copies `desktop/plugin.js` into `~/.hermes/desktop-plugins/sightline/`.
   For a linked checkout (`ln -s ~/sightline ~/.hermes/plugins/sightline`) every save
   re-syncs. Otherwise use **Capabilities → Plugins → Rescan**.
3. Desktop halves ship opt-in: turn Sightline on in **Capabilities → Plugins**.

## SDK APIs used

`PANES_AREA`, `PALETTE_AREA`, `STATUSBAR_AREAS.right`, `ctx.registerMany`,
`ctx.rest`, `ctx.onEvent`, `ctx.onDispose`, `ctx.os.openExternal`,
`host.revealPane`, `host.notify`, `useQuery`, `useMutation`, `queryClient`,
`relativeTime`, UI kit `Badge`, `Button`, `CopyButton`, `EmptyState`. Python:
`hermes_cli.plugin_events.broadcast_plugin_event`, the `dashboard/manifest.json`
+ `plugin_api.py` backend mount.

## Where the docs and the code differ (Hermes v0.23.0, 2bd378ed)

- The plugin guide has no "Talk to your own frontend: plugin RPC methods and
  session events" section, and the Python `PluginContext` has no RPC-method
  registrar. The working path is the dashboard backend mount (`plugin_api.py`,
  reached with `ctx.rest`) plus `broadcast_plugin_event`. "`sightline.get_state`"
  is `GET /state`; "`sightline.revoke_grant`" is `POST /revoke`.
- `ctx.emit()` exists on the Python context but publishes on the in-process
  plugin event bus (`<plugin>:<event>`), not to Desktop.
- The SDK page points agents at a bundled `hermes-desktop-plugins` skill; it is not
  in this checkout.
- Disk plugins are not scanned by Tailwind (stated in the radio example, not on the
  SDK page), so utility classes like `p-3` in the quick start only work when the app
  already uses them. Sightline keeps its layout in a small stylesheet that uses only
  `--ui-*` theme variables.
- The SDK page's delivery table says tools, hooks and slash commands in the agent
  turn reach every connected Desktop window. With `plugins.isolation: host` they run
  in the plugin-host child, which has no event relay (`hermes_cli/plugin_host*.py`),
  so the event is dropped silently (debug log only).
- With `plugins.isolation: host`, `validate` reports the backend runs through the
  plugin host with buffered responses; `ctx.socket` would not work there, which is
  why Sightline uses the global event stream instead.
