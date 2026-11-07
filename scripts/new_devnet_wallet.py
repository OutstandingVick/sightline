"""Generate a devnet wallet for Sightline and request a 1 SOL airdrop.

Usage: python scripts/new_devnet_wallet.py [--rpc URL] [--no-airdrop]

Prints the public key and the base58 secret. Put the secret in SIGHTLINE_SECRET_KEY
(e.g. ~/.hermes/.env). Never commit it.
"""

from __future__ import annotations

import argparse
import time

from solana.rpc.api import Client
from solana.rpc.commitment import Confirmed
from solders.keypair import Keypair

DEVNET = "https://api.devnet.solana.com"
FAUCET = "https://faucet.solana.com"
LAMPORTS_PER_SOL = 1_000_000_000


def airdrop(client: Client, kp: Keypair, sol: float = 1.0) -> bool:
    try:
        sig = client.request_airdrop(kp.pubkey(), int(sol * LAMPORTS_PER_SOL)).value
        for _ in range(30):
            status = client.get_signature_statuses([sig]).value[0]
            if status and status.confirmation_status:
                break
            time.sleep(1)
        bal = client.get_balance(kp.pubkey(), commitment=Confirmed).value
        print(f"Airdrop sent: {sig}\nBalance: {bal / LAMPORTS_PER_SOL} SOL")
        return bal > 0
    except Exception as exc:  # rate limits surface as RPC errors / HTTP 429
        print(f"Airdrop failed ({type(exc).__name__}: {exc}).")
        print(f"Fund it manually at {FAUCET} with address {kp.pubkey()}")
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rpc", default=DEVNET)
    ap.add_argument("--no-airdrop", action="store_true")
    a = ap.parse_args()

    kp = Keypair()
    print(f"Public key:  {kp.pubkey()}")
    print(f"Secret (b58): {kp}")
    print("Set SIGHTLINE_SECRET_KEY to the secret above. Keep it out of git.")
    if not a.no_airdrop:
        airdrop(Client(a.rpc), kp)


if __name__ == "__main__":
    main()
