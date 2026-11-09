# Changelog

## 0.5.0 — Phase 5: Desktop pane
- `desktop/plugin.js`: Hermes Desktop pane with network badge, wallet + balances, active grants
  (usage bar, countdown, Revoke) and a live, newest-first activity feed with explorer links.
- ⌘K "Sightline: Open firewall" and a status-bar item (`Sightline • N grants • last: …`).
- `dashboard/plugin_api.py`: `GET /state` (read-only) and `POST /revoke`. No route creates or
  widens a grant.
- `plugin.sightline.audit` event after every committed audit write; rollbacks emit nothing.
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
