# Simulation (Phase 2)

## Approach for balance changes

`simulate.py` calls `simulateTransaction` as raw JSON-RPC with
`sigVerify: false`, `replaceRecentBlockhash: true`, `commitment: confirmed` and an
`accounts` config (base64) for our wallet, the token accounts involved, the
recipient and every writable account.

We use the response's own `preBalances`/`postBalances` and
`preTokenBalances`/`postTokenBalances` (present on the devnet RPC, version 4.4).
They come from one atomic simulation, so there is no race between a separate
"pre" fetch and the simulation, and no hand-decoding of account bytes. If an RPC
omits or nulls any of the four fields, the report is `ok=false` (fail closed).

The `accounts` post-state is still used for one thing: an account that goes from
0 lamports to funded **with data** (`space > 0`) counts as created (and its
lamports as rent). A plain SOL recipient being funded does not.

## RPC / library quirks

- solana-py 0.36 / solders 0.26 `SimulateTransactionResp` drops the four balance
  fields and `fee`, hence raw JSON-RPC via httpx.
- `accounts` with `jsonParsed` through solana-py panics inside solders
  ("Cannot decode JsonParsed here"). We request base64 and only read `space`.
- `getFeeForMessage` returns `null` for a message whose blockhash has expired;
  we then fall back to the simulation's `fee` field.
- Devnet ATA rent is 1,488,440 lamports (0.00148844 SOL), not mainnet's familiar
  2,039,280. Never hard-code rent; read it from the simulation.
- `postBalances[0]` already has the fee deducted, so `sol_delta_lamports`
  includes it.

## Firewall inputs (Phase 4)

`Receipt.simulation` / `Preview.simulation` is the `SimulationReport` that was
approved; `explain.mismatches(intent, report)` returns the list Phase 4 blocks
on. `SimulationReport.from_dict` restores a stored report. Schema and a sample
are in [simulation-report.md](simulation-report.md).
