# Changelog

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
