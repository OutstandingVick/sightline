# Changelog

## 0.6.6 — catalog review fixes
- `hermes sightline setup` no longer writes the new key into `os.environ` on the Hermes path:
  `save_env_value` already publishes it to the active profile, and the shared process environment is
  readable by every profile on a multi-profile gateway. Only the standalone script sets it.
- Grants must match their `grant_created` audit entry to authorise anything; a `grant_revoked` entry
  can't be undone by editing the row; a log that fails verification disables every grant.
- Docs: the "model cannot create or widen grants" guarantee is scoped to Sightline's own tools. With
  Hermes' local terminal backend the agent's shell could read the key in `.env` or edit `data.db`;
  use a sandboxed terminal backend or terminal approvals for real funds.

## 0.6.5 — budgets and a clearer README
- Budgets: `/sightline grant <cap> <token> per week|month …` applies the cap per rolling 7 or 30 days
  (default stays 24h). Spend is summed from the audit log over the grant's period; a weekly or monthly
  grant lasts at least one period unless `for` says otherwise. Grant text, list, log, status tool and
  the Desktop pane show the period.
- README leads with what Sightline does (three bullets), the demo GIF and the judges' path; reference
  tables moved under "Reference". New cards from the live runs: unattended cron payments and a weekly
  budget.
- Live: weekly budget on devnet (two payments sent, the third refused at the 7d cap).

## 0.6.4 — Solana Pay links and unattended payments
- `sightline_pay` / `sightline_preview` take a Solana Pay transfer link (`link`): recipient, amount,
  `spl-token`, `memo` (Memo instruction) and `reference` keys (read-only accounts on the transfer).
  The preview names the payee from `label` and shows the memo. Transaction-request links, links
  without an amount and links that disagree with other arguments are refused. The approval cache
  is keyed on the exact link.
- Firewall: a payment to the wallet's own address is a clear `self_payment` BLOCK.
- Docs: Solana Pay links, unattended payments under a grant (live cron run), and a warning against
  `approvals.cron_mode: approve` / `single_query_mode: approve`.

## 0.6.3 — docs only
- Demo GIF at the top of the README, built from the real Desktop pane screenshots.
- Cropped pane screenshots (`docs/screenshots/pane-*.png`).
- "Judges: the 2-minute path" box with expected results for a funded and an empty wallet.

## 0.6.2
- Declare `requires_hermes: ">=0.23.0"` (the version Sightline is built and tested on).

## 0.6.1 — pre-ship fixes
- Firewall reports its policy verdict before simulation: mainnet opt-in, drain (`amount: "all"`, or an
  amount that would leave < 0.01 SOL), then the grant check. With an empty wallet a payment is still
  BLOCKed (fail closed), but the reason now reads e.g. "no grant covers this: … (Also: wallet has 0 SOL
  — run `hermes sightline setup` for funding options.)" instead of only "insufficient funds".
- `sightline_pay` / `sightline_preview` accept `amount: "all"`, which is always blocked as a drain.
- `SimulationReport.sol_pre_lamports`.
- README "Get devnet SOL" step; `hermes sightline setup` prints the same faucets (faucet.solana.com,
  QuickNode, Alchemy) and says what still works without funds.

## 0.6.0 — Phase 6: hardening for first-time users
- `/sightline setup` (and `scripts/setup_devnet.py`): creates or keeps a devnet wallet, stores the key
  through Hermes, airdrops with retry/backoff, prints web faucets when rate-limited. Never shows the key.
- Every error is `{error, message, next_step}`; hook BLOCK messages end with `Next: …`. New codes:
  `empty_wallet`, `insufficient_token`, `unknown_token`, `rpc_timeout`; `SimulationReport.error_code`.
- `SIGHTLINE_SECRET_KEY` also accepts a Solana CLI JSON byte array.
- Mainnet: previews and blocks start with `⚠ MAINNET — real funds`; status/balance carry a warning.
- Fixes: a token shortfall was reported as missing SOL; a repeated "Blockhash not found" was a generic
  send failure; RPC error text could include the RPC URL's query string (API keys).
- One vocabulary (ALLOW / APPROVE / BLOCK, grant, firewall) and one amount format everywhere.
- README rewritten; `pytest -m attack` selects the adversarial tests.

## 0.5.0 — Phase 5: Desktop pane
- `desktop/plugin.js`: Hermes Desktop pane with network badge, wallet + balances, active grants
  (usage bar, countdown, Revoke) and a live, newest-first activity feed with explorer links.
- ⌘K "Sightline: Open firewall" and a status-bar item (`Sightline • N grants • last: …`).
- `dashboard/plugin_api.py`: `GET /state` (read-only) and `POST /revoke`. No route creates or
  widens a grant.
- `plugin.sightline.audit` event after every committed audit write; rollbacks emit nothing.
  Events don't leave the plugin host, so the pane also re-reads `/state` every 5 s.
- Status bar shows `Sightline • offline` when the backend can't be reached.
- `scripts/check.sh` runs every offline check; JS tests for the Desktop half.
- Fix: grant usage shown as `100`, not `1E+2`.

## 0.4.0 — Phases 3+4: grants, firewall, audit log
- Human-only `/sightline` command: grant, grants, revoke (incl. picker / all), log, verify.
- Grants: per token and network, named recipients (or explicit `any`), per-tx max, rolling 24h
  cap computed from the audit log, expiry and revocation checked at decision time.
- Firewall: hard blocks (simulation, mismatch, unknown programs, authority/approve/close/assign,
  SOL reserve, >90% of a token balance, mainnet), grant ALLOW, otherwise human APPROVE.
- `pre_tool_call` hook on `sightline_pay` only; unique approval keys so "always" can't
  become a blanket approval; second gate + atomic spend reservation in `execute_intent`.
- Append-only hash-chained audit log; unanswered approvals shown as blocked.
- `sightline_status` lists grants read-only.

## 0.3.0 — Phase 2: simulation + plain-English preview
- `simulate.py`: raw `simulateTransaction` (sigVerify off, blockhash replaced) → `SimulationReport`
  with fee, our SOL/token deltas, programs, writable/created accounts, rent, slot.
- `explain.py`: 1–3 line preview plus `⚠ Mismatch:` when simulated effects differ from the intent;
  unknown programs flagged.
- `execute_intent`: build → simulate → sign/send; any simulation or RPC failure sends nothing.
- New tool `sightline_preview` (never signs). Receipts carry the approved report.
- Balance pre-checks removed from builders; simulation is the single gate.

## 0.2.0 — Phase 1: wallet core
- `sightline_balance`: SOL + SPL balances (Token and Token-2022), known symbols per cluster.
- `sightline_pay`: SOL, known symbol or mint; idempotent recipient ATA; transfer_checked.
- `execute_intent` choke point between build and sign/send for simulation and firewall.
- Mainnet refused unless `SIGHTLINE_ALLOW_MAINNET=1`; custom RPCs checked by genesis hash.
- Decimal-only amount math; structured errors; blockhash-expiry rebuild + retry once.
- Offline test suite with a fake RPC; opt-in live devnet test.
- `scripts/create_test_mint.py` for a devnet SPL test token.

## 0.1.0 — Phase 0: skeleton
- Plugin manifest, `sightline_status`, placeholder `pre_tool_call` hook.
