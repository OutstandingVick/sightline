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

**"simulation_failed".** Nothing was sent. The message and `logs` say why
(usually insufficient SOL or tokens). Use `sightline_preview` to dry-run.

**Airdrop rate-limited.** Use https://faucet.solana.com.

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
