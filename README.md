# Sightline

A Solana transaction firewall for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

The agent gets intent-level wallet tools (balance, pay, later swap). Every signing
call passes a `pre_tool_call` hook that checks a user-issued, time-boxed, revocable
grant, simulates the transaction, explains it in plain English, and blocks or
approves it. The private key never reaches the model. Devnet by default.

**Status: WIP (Phase 1 — wallet core).** Balances and SOL/SPL payments work on
devnet. Grants, simulation and the firewall come in later phases; the
`pre_tool_call` hook is still a logging placeholder.

## Tools

| Tool | What it does |
|---|---|
| `sightline_status` | Network, RPC URL, wallet public key |
| `sightline_balance` | SOL + all SPL token balances (symbol when known) |
| `sightline_pay(recipient, amount, token="SOL")` | Send SOL, a known symbol (`USDC`) or any mint; creates the recipient's token account if missing; returns signature + explorer link |

No tool accepts raw transactions or instructions, and the secret key is never
returned. Every payment goes through one choke point, `intents.execute_intent`.

Mainnet is refused unless `SIGHTLINE_ALLOW_MAINNET=1`; a custom RPC is checked
against the mainnet genesis hash.

## Install (local)

```bash
git clone https://github.com/OutstandingVick/sightline ~/sightline
ln -s ~/sightline ~/.hermes/plugins/sightline
hermes plugins enable sightline   # installs solana + solders
```

Set your wallet in `~/.hermes/.env`:

```
SIGHTLINE_SECRET_KEY=<base58 keypair>
# optional, defaults to https://api.devnet.solana.com
SIGHTLINE_RPC_URL=
# optional, mainnet is refused unless set to 1
SIGHTLINE_ALLOW_MAINNET=
```

After changing plugin code, restart Hermes (`hermes gateway restart`) so the
gateway reloads it.

Then ask Hermes: *"what's my sightline status?"*

## Devnet wallet

```bash
python scripts/new_devnet_wallet.py
```

Generates a keypair, prints the public key and base58 secret, and requests a
1 SOL airdrop. If the faucet rate-limits you, fund the address at
https://faucet.solana.com.

For an SPL token, see [docs/devnet-tokens.md](docs/devnet-tokens.md)
(`scripts/create_test_mint.py`, or devnet USDC from https://faucet.circle.com).

## Development

```bash
pip install "solana>=0.36,<0.37" "solders>=0.26,<0.27" pytest pyyaml
pytest                              # offline, RPC is faked
SIGHTLINE_LIVE_TESTS=1 pytest tests/test_live_devnet.py   # sends 0.001 devnet SOL
hermes plugins doctor . --ci
hermes plugins validate . --install-deps
```

## Disclosures

- Makes network calls to the configured Solana RPC (devnet by default).
- Reads `SIGHTLINE_SECRET_KEY` via Hermes' secret route; never returns it to the model.

## License

MIT
