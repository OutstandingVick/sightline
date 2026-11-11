# Security model

Sightline closes the loop **permission → enforcement → revocation → verifiable record**.

## Who can do what

| Actor | Can | Cannot |
|---|---|---|
| Human (slash command) | `/sightline grant`, `grants`, `revoke`, `log`, `verify` | — |
| Human (Desktop pane) | view state, revoke a grant | create, widen or extend a grant (no such route) |
| Model (tools) | read status + grants, balance, preview, request a payment | create, widen, extend or revoke a grant; sign arbitrary transactions |

There is no model-callable tool that writes grants or policy
(`tests/test_model_cannot_grant.py`), and the Desktop backend has exactly two
routes, `GET /state` and `POST /revoke` (`tests/test_plugin_api.py`). Slash commands run only when a person
types them.

## Enforcement path for `sightline_pay`

1. **`pre_tool_call` hook** (gate.py): parse args → intent → build → simulate →
   `firewall.decide`. BLOCK returns Hermes' `block` directive; APPROVE returns
   `approve` with the plain-English preview; ALLOW returns nothing. Any exception
   blocks (fail closed).
2. **Hermes approval gate** for APPROVE. Each request carries a unique `rule_key`,
   so answering "always" or "session" can never become a blanket approval for
   later payments. With nobody to answer (cron, `-q`, gateway without a user),
   Hermes blocks.
3. **Second gate in `execute_intent`**: the firewall runs again inside a
   `BEGIN IMMEDIATE` transaction under a process lock, together with the spend
   reservation, so two parallel calls can't both fit under one cap. An APPROVE
   verdict proceeds only if the hook asked a human about this exact call
   (session + arguments, single use, 30 s). If the hook never ran, APPROVE is a
   BLOCK.

## Hard blocks (no grant or approval overrides them)

- simulation failed, RPC error, or balance data missing
- simulated effects differ from the request (`explain.mismatches`)
- a program outside System, Token, Token-2022, Associated Token, Compute Budget, Memo
- approve / set-authority / close-account / assign instructions, or undecodable ones
- SOL balance would drop below 0.01 SOL
- more than 90% of a token balance in one transaction
- mainnet without `SIGHTLINE_ALLOW_MAINNET=1`

## Record

The audit log is append-only and hash-chained (audit.py). Grant creation and
revocation, every firewall decision (hook and second gate), every reservation and
its outcome are recorded. A grant's 24h spend is computed from this log, not kept
as a counter. `/sightline verify` recomputes the chain and reports the first
broken entry.

## Known limits (disclose to users)

- **Local tampering.** The database lives in Hermes' plugin data directory. An
  agent that also has unrestricted shell access could write to it or to Hermes'
  config. Hermes' own terminal approvals are the guard there; `/sightline verify`
  detects edits to past audit entries but not a forged grant row inserted
  together with a rebuilt chain. Keep shell tools on approval mode when Sightline
  holds real value.
- **`approvals.single_query_mode: approve`** (for `-q` runs) and **`approvals.cron_mode:
  approve`** (for cron jobs) in Hermes' config auto-approve plugin approval requests when
  nobody is present. Leave both unset: without them, an unattended run can pay only inside
  a grant ([unattended payments](unattended-payments.md)).
- **Solana Pay links** are parsed into the same intent as a typed payment; a link can't
  widen a grant, an approval is bound to the exact link, and transaction-request links
  (`solana:https://…`), which would hand Sightline a ready-made transaction, are refused.
- **Hermes trusts the plugin process.** Sightline runs in-process (plugin host
  isolation), like every native plugin.
- **Desktop access.** Anyone using the Desktop window can see the wallet address,
  balances and history, and can revoke grants. They cannot create or widen one.
- Devnet by default; mainnet must be opted into explicitly.
