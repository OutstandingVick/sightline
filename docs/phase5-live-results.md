# Phase 5 live results — Desktop pane (devnet, 2026-11-09)

Hermes Agent v0.23.0 (2bd378ed). Hermes Desktop was built from that checkout with
`hermes desktop --build-only` and driven over CDP to take screenshots. The plugin
is linked (`~/.hermes/plugins/sightline → ~/sightline`), so Desktop's copy in
`desktop-plugins/sightline/` re-synced on every save.

Payments ran from the CLI (`hermes chat -q`, free longcat model), because the
Desktop chat's default free model was rate-limited. Grants and revokes were done
in Desktop: the slash command in its composer and the Revoke button in the pane.
Recipient `76nKQ7uBMB482NqeVxUjyNXbq2kq741TmbKM9umLTRX1`.

| Step | Where | Pane shows | Screenshot |
|---|---|---|---|
| No active grants | — | empty state with the `/sightline grant …` hint | `01-no-grants-*` |
| `/sightline grant 0.03 SOL to 76nK… for 1h max 0.01 note demo` | Desktop composer | card `g_e210`, 0 / 0.03 used, countdown, Revoke | `02-grant-created-*` |
| send 0.01 SOL | CLI | green ALLOW (hook + second gate), SIGNING, SENT + Explorer link; bar at 0.01 / 0.03 | `03-allow-sent-*` |
| send 4.925 SOL ("whole balance") | CLI | red BLOCK, "would leave less than the 0.01 SOL reserve · rule: sol_reserve" | `04-block-*` |
| click **Revoke** | pane | toast "Revoked g_e210", card dimmed, REVOKED row | `05-revoked-*` |
| send 0.01 SOL | CLI | amber APPROVE, "grant g_e210 revoked … · rule: no_grant"; `-q` has nobody to approve, so nothing was sent | `06-approve-after-revoke-*` |

Signatures from this run: `3fRBBttu…r6ECd` (g_e210), plus earlier runs
`2qqvRBLC…oeVS` (g_2137) and `kXGvb5vn…8gn5` (g_05fe). The audit chain verified ✓
throughout.

## How fast the pane updated

A grant made in the Desktop composer appeared in the pane 1.9–6.4 s later. That
comes from the 5 s poll, not from the event: Sightline's code runs in the
plugin-host child, which drops `broadcast_plugin_event` (see
[desktop-pane.md](desktop-pane.md)). Revoking from the pane refreshes it at once,
because the pane refetches straight after the call.

## Checks

- `hermes plugins doctor . --ci`: OK, 4 tools and 1 hook, no stale desktop copy warning.
- `hermes plugins validate . --install-deps`: passed, including `desktop surface`.
  One note: the dashboard backend is served through the plugin host (buffered responses).
- `pytest`: 183 passed, 2 skipped (live devnet tests are opt-in).
  `node --test tests/js/*.test.mjs`: 7 passed.

## Found and fixed along the way

- Grant usage rendered as `1E+2` instead of `100` (`Decimal.normalize`).
- The copy button's label overlapped the wallet address; now icon-only.
- One BLOCK reason read `0.010000000 SOL`. A long-running gateway was still serving
  Phase 3 code; `hermes gateway restart` fixed it.
