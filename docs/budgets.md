# Budgets: caps per day, week or month

A grant's cap applies over a rolling period: 24 hours by default, or a week or a month.

```text
/sightline grant <cap> <token> [per day|week|month] to <addr>[,<addr>]|any [for <duration>] [max <per_tx>] [note "…"]
```

| You want | Command |
|---|---|
| a weekly allowance | `/sightline grant 5 USDC per week to <alice> max 2 note "allowance"` |
| a monthly subscription | `/sightline grant 10 USDC per month to <service> max 10 for 90d` |
| a supplier budget, any of three addresses | `/sightline grant 50 USDC per month to <a>,<b>,<c> max 20 for 180d` |

- **Rolling, not calendar.** "Per week" means "in the last 7 days" at the moment of each
  payment, so there's no reset moment to game.
- **Computed from the audit log.** Spend is summed from the hash-chained log (failed sends
  don't count), so it can't drift from what was actually sent.
- **Expiry.** Without `for`, a weekly or monthly budget lasts one period; with `for` it lasts as
  long as you say. Revoke any time from chat, `hermes sightline revoke`, or the Desktop pane.
- **Splitting doesn't help.** Many small payments still add up against the same cap; the
  per-payment `max` bounds each one.

Inside the budget, payments go through on their own, including from cron jobs and bots
([unattended payments](unattended-payments.md)). The payment that would exceed it gets
APPROVE: Hermes asks you, or refuses when nobody is there.

Live run (devnet, 2026-11-11): `/sightline grant 0.02 SOL per week to CYFK…EsxE max 0.01`, then
three unattended `send 0.01 SOL` requests: ALLOW (sent), ALLOW (sent), then APPROVE "exceeds the 7d
cap of grant g_07a8: 0.02/0.02 used" and refused. Details: [v0.6.5-live-results.md](v0.6.5-live-results.md).
