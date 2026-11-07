# Notes for Phase 2 (simulation)

Probed `simulateTransaction` on devnet with a built `sightline_pay` SPL transfer
(idempotent ATA create + transfer_checked, v0 message).

- The raw JSON-RPC response **does** include `preBalances`, `postBalances`,
  `preTokenBalances`, `postTokenBalances` and `fee`, plus `accounts`, `logs`,
  `unitsConsumed`, `innerInstructions`, `replacementBlockhash`.
- solana-py 0.36 / solders 0.26 `SimulateTransactionResp` **drops** the
  balance fields and `fee`. Use a raw JSON-RPC call (httpx POST) to keep them.
- Asking for `accounts: {encoding: "jsonParsed", addresses: [...]}` through
  solana-py **panics** in solders ("Cannot decode JsonParsed here"). Via raw
  JSON-RPC it works and returns post-state of the listed accounts (e.g. the
  recipient ATA's parsed `tokenAmount`, the payer's lamports).
- Use `sigVerify: false, replaceRecentBlockhash: true` so the unsigned tx built
  by `wallet.build_*` can be simulated without the key.
- The choke point is `intents.execute_intent`, between `build()` and
  `wallet.sign_and_send()`.
