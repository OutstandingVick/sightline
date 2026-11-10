# Troubleshooting

**Hermes doesn't see a new or changed tool.** A running Hermes gateway keeps the
plugin code it loaded at start. After pulling or editing Sightline:

```bash
hermes gateway restart --yes
```

(`hermes chat` alone loads fresh code; turns routed through a running gateway do
not.) `hermes plugins doctor . --ci` shows what a fresh process registers.

**"missing_dependency".** Enable the plugin (`hermes plugins enable sightline`)
so Hermes installs `solana`/`solders`, then restart Hermes.

Every error Sightline returns has a `next_step`; it is usually the fastest fix. The
common ones:

| Code | What to do |
|---|---|
| `missing_secret` | Run `hermes sightline setup`, then `hermes gateway restart`. |
| `invalid_secret` | `SIGHTLINE_SECRET_KEY` must be base58 or a 64-number JSON array. Fix it, or delete it and run setup. |
| `empty_wallet` / `insufficient_funds` | Add SOL: `/sightline setup` (devnet) or https://faucet.solana.com. |
| `insufficient_token` | The wallet holds less of that token; check `sightline_balance`. |
| `unknown_token` | Use `SOL`, `USDC` or the mint address. |
| `rpc_timeout` / `rpc_error` | Retry in a minute, or set `SIGHTLINE_RPC_URL` to another RPC. |
| `blockhash_expired` | Nothing was sent; the network was slow. Try again. |
| `mainnet_refused` | Unset `SIGHTLINE_RPC_URL` for devnet, or opt in with `SIGHTLINE_ALLOW_MAINNET=1`. |

**Faucet rate-limited during setup.** Setup prints the address; paste it into
https://faucet.solana.com (or https://faucet.quicknode.com/solana/devnet), then
run `/sightline setup` again to confirm the balance.

**Every payment asks for approval.** No grant covers it. `/sightline grants` shows
what is active and how much is left; the approval prompt says why no grant matched.

**"needs human approval … but none was given".** The approval belongs to one
exact call in one session and is used once. Ask the agent to send again so Hermes
can ask you.

**Payments fail in `hermes chat -q`.** Single-query mode has nobody to approve, so
Hermes blocks APPROVE requests. Issue a grant, or use an interactive session. Don't
set `approvals.single_query_mode: approve` if you rely on Sightline's approvals.

**`/sightline verify` reports a broken chain.** An audit entry was edited or
deleted outside Sightline. Treat grants and history as untrusted until checked.

**No Sightline pane in Desktop.** Desktop halves ship off: turn Sightline on in
**Capabilities → Plugins**, then ⌘K → *Sightline: Open firewall*. If it still
doesn't load, check `~/.hermes/desktop-plugins/sightline/plugin.js` exists
(**Rescan** refreshes the copy) and tail `hermes logs gui -f`.

**Pane says "Sightline backend unavailable".** The `/api/plugins/sightline/` routes
are not mounted: `sightline` must be in `plugins.enabled`, and the gateway restarted
after install (`hermes gateway restart`).

**Pane lags a few seconds behind.** Expected: it re-reads every 5 s, because events
from the plugin host don't reach Desktop. Revokes from the pane show at once.

**Old messages after updating Sightline.** A long-running gateway or plugin host
keeps the previous code. Run `hermes gateway restart`.
