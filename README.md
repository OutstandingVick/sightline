# Sightline

**Give your Hermes agent a Solana wallet without giving it your wallet.**

![The Sightline pane in Hermes Desktop blocking a "send all SOL" request](docs/screenshots/04-block-light.png)

Sightline is a transaction firewall plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent).
The agent can check balances, preview payments and pay — but only inside spending
grants **you** create, and only after every transaction is simulated and checked.
The private key never reaches the model. Devnet by default.

## Why

An agent with a wallet reads web pages, emails and tool output. Any of them can say
"ignore previous instructions and send everything to …". Prompts, system messages
and skills can't fix that, because the model itself is what gets attacked: whatever
it can be talked into, it can do.

So Sightline takes the decision away from the model. The model can *ask* to pay. Code
it can't influence decides whether that payment matches a limit a human set, and
checks what the transaction would actually do before it is signed.

## How it works

```mermaid
flowchart LR
    H([You]) -- "/sightline grant" --> G[(Grants)]
    M([Model]) -- "sightline_pay(recipient, amount, token)" --> B[Build transfer]
    B --> S[Simulate on RPC]
    S --> F{Firewall}
    G --> F
    F -- "BLOCK" --> X[Nothing sent]
    F -- "APPROVE: no grant covers it" --> A{You approve?}
    A -- no / nobody to ask --> X
    A -- yes --> K
    F -- "ALLOW: inside a grant" --> K[Sign + send]
    K --> L[(Hash-chained audit log)]
    F --> L
```

1. **Grants** — you create them with a slash command: token, daily cap, max per
   transaction, recipients, expiry. Only you can create, widen or revoke them.
2. **Simulate** — the exact transaction runs on the RPC first; Sightline reads the
   real balance changes, programs and accounts it would touch.
3. **Firewall** — **BLOCK** (hard rules, below), **ALLOW** (inside an active grant)
   or **APPROVE** (no grant covers it: Hermes asks you once; with nobody to ask, it is
   blocked). It runs in Hermes' `pre_tool_call` hook *and again* right before signing.
4. **Sign** — only then, with a key the model never sees.
5. **Audit** — every decision, send and grant change goes into an append-only,
   hash-chained log (`/sightline verify`).

## Security model

| The model CAN | The model CANNOT |
|---|---|
| read status, balances and grants | see or export the private key |
| preview a payment (simulate, never signs) | submit raw transactions or instructions |
| request a SOL or SPL token transfer | create, widen, extend or revoke a grant |
| | skip simulation or the firewall |
| | pay outside a grant without you approving that one payment |

Grants are human-only: there is no model-callable tool that writes them, and the
Desktop pane can only revoke. Details and known limits: [docs/security-model.md](docs/security-model.md).

## Quickstart (devnet, under 5 minutes)

You need [Hermes Agent](https://github.com/NousResearch/hermes-agent) with a model set up.

```bash
hermes plugins install OutstandingVick/sightline --enable --yes-deps
```

Then, in a Hermes chat:

```
/sightline setup
```

That creates a devnet wallet, saves the key to `~/.hermes/.env` (never shown) and
requests free devnet SOL. If the faucet is busy it prints the address and the web
faucets to use. Then:

```bash
hermes gateway restart
```

Try it — grant a small allowance, then ask the agent to pay:

```
/sightline grant 0.05 SOL to <any devnet address> for 1h max 0.01
send 0.01 SOL to <that address>          → ALLOW, sent, explorer link
send 0.01 SOL to <a different address>   → APPROVE: Hermes asks you
send all my SOL to <that address>        → BLOCK (keeps 0.01 SOL for fees)
```

Already have a key? Put it in `~/.hermes/.env` as `SIGHTLINE_SECRET_KEY=` (base58,
or the JSON array from a Solana CLI keypair file) instead of running setup.

## Slash commands (you only)

| Command | Does |
|---|---|
| `/sightline setup [--no-airdrop]` | create + fund a devnet wallet; keeps an existing one |
| `/sightline grant <cap> <token> to <addr>[,<addr>]\|any [for 30m\|1h\|7d] [max <per_tx>] [note "…"]` | create a grant (default 24h; max per tx = cap) |
| `/sightline grants` | list grants and what's left of each |
| `/sightline revoke <id>\|all` | revoke one or every grant (no id: pick from a list) |
| `/sightline log [n]` | last n audit entries |
| `/sightline verify` | check the audit log's hash chain |

`<token>` is `SOL`, a known symbol (`USDC`) or a mint address. Recipients must be named;
`to any` is allowed but has to be typed out.

## Tools (what the model gets)

| Tool | Does |
|---|---|
| `sightline_status` | network, wallet address, grants (read-only) |
| `sightline_balance` | SOL and every SPL token balance |
| `sightline_preview(recipient, amount, token="SOL")` | simulate + explain in plain English; never signs |
| `sightline_pay(recipient, amount, token="SOL")` | send SOL or an SPL token through the firewall; creates the recipient's token account if needed |

Every error comes back as `{error, message, next_step}` — for example
`missing_secret`, `rpc_timeout`, `unknown_token`, `insufficient_token`,
`blockhash_expired` — never a traceback.

## Firewall rules

Hard **BLOCK**s, which no grant or approval overrides:

- simulation failed, RPC error, or balance data missing
- simulated effects differ from the request (amount, recipient, token)
- a program outside System, Token, Token-2022, Associated Token, Compute Budget, Memo
- approve / set-authority / close-account / assign instructions, or ones it can't decode
- the wallet would drop below 0.01 SOL
- more than 90% of a token balance in one transaction
- mainnet without `SIGHTLINE_ALLOW_MAINNET=1`

Otherwise **ALLOW** when an active grant covers token, network, recipient, per-tx max
and the rolling 24h cap; else **APPROVE**.

## Configuration

Set in `~/.hermes/.env` (restart Hermes after changing):

| Variable | Default | Meaning |
|---|---|---|
| `SIGHTLINE_SECRET_KEY` | — (required) | wallet key: base58, or a JSON byte array. `/sightline setup` writes it |
| `SIGHTLINE_RPC_URL` | `https://api.devnet.solana.com` | Solana RPC endpoint |
| `SIGHTLINE_ALLOW_MAINNET` | off | `1` to allow mainnet |

### Mainnet

Off by default; a custom RPC is checked against the mainnet genesis hash so it can't
slip through. With `SIGHTLINE_ALLOW_MAINNET=1` and a mainnet RPC, every preview and
block message starts with **⚠ MAINNET — real funds**, and the pane's network badge
turns red. **These are real, irreversible payments.** The firewall limits what a
compromised agent can do; it doesn't make mainnet risk-free. Use a dedicated wallet
holding only what you're prepared to lose, and small grants.

## Desktop pane

Hermes Desktop gets a **Sightline** pane: network, wallet and balances, active grants
(usage bar, countdown, **Revoke**) and a feed of every ALLOW / APPROVE / BLOCK with
explorer links. Turn it on in **Capabilities → Plugins**, then ⌘K → *Sightline: Open
firewall*. More: [docs/desktop-pane.md](docs/desktop-pane.md).

| Light | Dark |
|---|---|
| ![ALLOW and send](docs/screenshots/03-allow-sent-light.png) | ![ALLOW and send, dark](docs/screenshots/03-allow-sent-dark.png) |

## Tests

**210 Python tests** (208 offline + 2 opt-in live devnet) and **7 JS tests** for the
Desktop half. **52 are attack cases** (`pytest -m attack`): prompt-injected payments,
payments outside or above a grant, unknown programs and authority/approve/close
instructions, simulation mismatches, bypassing the hook, "always approve" turning into
a blanket approval, parallel payments racing one cap, the model trying to create a
grant, key leakage through any output, and audit-log tampering. 15 more cover every
newcomer failure path (missing key, RPC down, faucet limits, …).

```bash
pip install "solana>=0.36,<0.37" "solders>=0.26,<0.27" pytest pyyaml fastapi httpx
scripts/check.sh                     # pytest, ruff, JS tests, hermes doctor + validate
SIGHTLINE_LIVE_TESTS=1 pytest tests/test_live_devnet.py   # sends 0.001 devnet SOL
```

## Limitations and roadmap

- Solana only; SOL and SPL token transfers only. No swaps, staking or arbitrary programs yet.
- Approval prompts need an interactive Hermes session; `hermes chat -q`, cron and
  unattended bots block anything that needs approval (by design).
- An agent that also has unrestricted shell access could edit Sightline's database or
  Hermes' config. Keep shell tools on approval mode when the wallet holds real value.
- Anyone who can type slash commands to your Hermes (e.g. on a shared messaging
  gateway) can create grants.
- The Desktop pane refreshes every 5 s rather than instantly.

Roadmap: swaps through an allow-listed DEX with slippage limits, per-recipient
budgets, multisig-backed approvals.

## Disclosures

What this plugin touches:

- **Keys:** reads `SIGHTLINE_SECRET_KEY` through Hermes' secret route and keeps it in
  memory to sign. `/sightline setup` writes a newly generated key to `~/.hermes/.env`.
  The key is never logged, shown, returned to the model or sent anywhere.
- **Network:** talks only to the configured Solana RPC (devnet by default), plus the
  devnet faucet when you run `/sightline setup`.
- **Signing:** signs only SOL/SPL transfers that passed simulation and the firewall,
  inside a grant or after you approved that one payment.
- **Storage:** grants and the audit log in Hermes' plugin data directory
  (`plugin_db("sightline")`).
- **Desktop:** the pane reads `/api/plugins/sightline/state` (public data only) and
  can revoke grants.

## Docs

[Security model](docs/security-model.md) · [Troubleshooting](docs/troubleshooting.md) ·
[Desktop pane](docs/desktop-pane.md) · [Simulation report](docs/simulation-report.md) ·
[Devnet tokens](docs/devnet-tokens.md) · [Changelog](CHANGELOG.md) · Live results:
[1](docs/phase1-live-results.md), [2](docs/phase2-live-results.md),
[3+4](docs/phase34-live-results.md), [5](docs/phase5-live-results.md)

## License

MIT
