# Devnet test tokens

Sightline needs an SPL token on devnet to test `sightline_pay`.

## Option A: test mint (what we used)

```bash
SIGHTLINE_SECRET_KEY=... python scripts/create_test_mint.py --amount 1000 --decimals 6
```

Creates a 6-decimal mint with the Sightline wallet as mint authority and mints
1000 tokens to its associated token account. Pay with the mint address:
"send 1 of token 53vs…dTNb to <addr>".

Phase 1 test mint: `53vsfWndMbUCWa4LknedEAHqZLxtLpvehpF3nPVedTNb`
(tx `2stAXgSvf7HwNDupeyzH7YgWQWsjhhbHtXKQnikpoTk6nHMVugDzLmYBPy4qT6uMgTFhnkkwTg1PhbbGiQJ6S2fv`).

## Option B: devnet USDC

Request devnet USDC for the wallet address at https://faucet.circle.com
(select Solana Devnet). The mint is `4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU`,
which Sightline already knows as `USDC`, so "send 1 USDC to <addr>" works.
