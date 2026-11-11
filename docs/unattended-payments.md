# Unattended payments (cron, bots)

The point of an agent wallet is paying when you're not there: a subscription every
morning, a supplier when an invoice arrives, a bot that tips. Sightline makes that safe
with the same grant you'd use interactively:

- **Inside a grant**, the firewall returns no directive at all, so Hermes runs the payment
  with nobody at the keyboard.
- **Outside a grant**, the firewall asks for human approval. A cron job or an unattended
  bot has no one to answer, so Hermes refuses and nothing is sent.

Nothing extra to configure: the grant *is* the standing permission.

## Example: a daily payment

```text
/sightline grant 0.3 SOL to 76nKQ7uBMB482NqeVxUjyNXbq2kq741TmbKM9umLTRX1 for 7d max 0.01 note "daily"
```

```bash
hermes cron create "0 9 * * *" \
  "Pay this Solana Pay link with sightline_pay, passing it as the link argument: solana:76nKQ7uBMB482NqeVxUjyNXbq2kq741TmbKM9umLTRX1?amount=0.01&memo=daily" \
  --name daily-payment --deliver local
```

Every morning the job pays 0.01 SOL with the memo `daily`. If the link is ever edited to
another recipient, a bigger amount, or the grant expires or is revoked, the run is
refused and `/sightline log` shows why. The rolling 24h cap (0.3 SOL here) bounds the
worst case even if the job misfires.

## Live run (devnet, 2026-11-11)

Two one-shot cron jobs on the same grant `g_7ff1` (0.03 SOL/24h, max 0.01, to `76nK…TRX1`):

| Job | Link | Result |
|---|---|---|
| A | `solana:76nK…TRX1?amount=0.01&label=Demo%20Cafe&memo=invoice-1001` | **ALLOW**, sent unattended: `3k1KjbyhGYxtZ5gtZbhFsHzMncG5oWZ2XDfTkmLq23F8o7hW7FAUesnhtCvPbT1ohMdbCqQwDDZHeyvqGeTVG3WW` (memo `invoice-1001` confirmed on chain) |
| B | `solana:67AY…M547?amount=0.01&label=Unknown%20Shop&memo=invoice-2002` | **APPROVE** → Hermes: "cron jobs run without a user present to approve it". Nothing sent. |

## Don't undo it

Hermes has settings that approve flagged actions automatically when nobody is present:
`approvals.cron_mode: approve` (cron) and `approvals.single_query_mode: approve`
(`hermes chat -q`). With either set, every APPROVE becomes a yes and the grant stops being
the limit. Leave them unset. In the live run above, Hermes itself suggested
`cron_mode: approve`; the agent correctly declined to change it.
