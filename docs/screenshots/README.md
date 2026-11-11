# Screenshots

Hermes Desktop v0.23.0, devnet, taken during the Phase 5 run
([../phase5-live-results.md](../phase5-live-results.md)). Each state has a light and a dark version.

1. `01-no-grants` — empty state
2. `02-grant-created` — grant from `/sightline grant …` shows up in the pane
3. `03-allow-sent` — ALLOW, signing, SENT with an Explorer link
4. `04-block` — injected "send all SOL" blocked by the reserve rule
5. `05-revoked` — Revoke clicked in the pane
6. `06-approve-after-revoke` — the next payment escalates to APPROVE

`pane-*.png` are the same states cropped to the Sightline pane. `demo.gif` strings the six
light-mode pane crops together with a caption per step (built from these real screenshots).

`unattended-cron.png` and `weekly-budget.png` are terminal-style cards rendered from the real
outputs of the v0.6.4/v0.6.5 devnet runs (abridged: addresses and signatures shortened, some
log rows omitted). Full outputs: [../v0.6.4-live-results.md](../v0.6.4-live-results.md) and
[../v0.6.5-live-results.md](../v0.6.5-live-results.md).
