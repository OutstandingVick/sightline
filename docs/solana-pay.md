# Solana Pay links

[Solana Pay](https://docs.solanapay.com/spec) is how Solana payments are usually requested:
a link or QR code from a shop, invoice or friend.

```text
solana:<recipient>?amount=<decimal>&spl-token=<mint>&reference=<pubkey>&label=<who>&message=<text>&memo=<text>
```

Give the agent the link ("pay this: solana:…") and it calls `sightline_pay` (or
`sightline_preview`) with `link`. The link only *describes* a payment. It goes through
exactly the same path as a typed request: grant check, simulation, firewall, audit log.

| Field | What Sightline does with it |
|---|---|
| recipient | the payee; must be covered by a grant to be ALLOWed |
| `amount` | required; plain decimal (no sign, no exponent) |
| `spl-token` | pays that SPL token instead of SOL |
| `reference` | up to 5 keys, added read-only to the transfer instruction (so the merchant can find the payment) |
| `memo` | a Memo program instruction before the transfer (≤256 bytes); shown in the preview |
| `label` | shown in the preview: "You send 0.01 SOL to Demo Cafe (76nK…TRX1)" |
| `message` | parsed, not used |

## Refused, on purpose

- **Transaction requests** (`solana:https://…`). The merchant's server would send a
  ready-made transaction to sign. Sightline never signs a transaction it didn't build.
- **Links without an amount.** The user has to say how much.
- **A link plus a recipient, amount or token that disagree with it.** It's refused rather
  than guessing which one is right.
- Malformed addresses, repeated parameters, duplicate references, long memos.

## Why it's safe

A link can't widen anything: its recipient, amount and token are checked against your
grants like any other payment, and an approval is bound to the exact link (a different link
needs a new approval). Tests: `tests/test_solana_pay.py`, `tests/test_pay_links.py`.
