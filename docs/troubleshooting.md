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
