# Sightline

A Solana transaction firewall for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

The agent gets intent-level wallet tools (balance, pay, later swap). Every signing
call passes a `pre_tool_call` hook that checks a user-issued, time-boxed, revocable
grant, simulates the transaction, explains it in plain English, and blocks or
approves it. The private key never reaches the model. Devnet by default.

**Status: WIP (Phase 0 — skeleton).** Only `sightline_status` and a logging
`pre_tool_call` hook exist today.

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
```

Then ask Hermes: *"what's my sightline status?"*

## Devnet wallet

```bash
python scripts/new_devnet_wallet.py
```

Generates a keypair, prints the public key and base58 secret, and requests a
1 SOL airdrop. If the faucet rate-limits you, fund the address at
https://faucet.solana.com.

## Development

```bash
pip install "solana>=0.36,<0.37" "solders>=0.26,<0.27" pytest pyyaml
pytest
hermes plugins doctor . --ci
hermes plugins validate . --install-deps
```

## Disclosures

- Makes network calls to the configured Solana RPC (devnet by default).
- Reads `SIGHTLINE_SECRET_KEY` via Hermes' secret route; never returns it to the model.

## License

MIT
