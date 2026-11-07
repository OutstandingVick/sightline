"""Create a devnet SPL test token and mint some to the Sightline wallet.

Usage: SIGHTLINE_SECRET_KEY=... python scripts/create_test_mint.py [--amount 1000] [--decimals 6]

The wallet pays for and is the mint authority. Prints the mint address; pass it to
sightline_pay as `token`. Devnet only.
"""

from __future__ import annotations

import argparse
import os
import sys

from solana.rpc.api import Client
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TxOpts
from solders.keypair import Keypair
from solders.message import MessageV0
from solders.system_program import CreateAccountParams, create_account
from solders.transaction import VersionedTransaction
from spl.token.constants import TOKEN_PROGRAM_ID
from spl.token.instructions import (
    InitializeMint2Params,
    MintToCheckedParams,
    create_idempotent_associated_token_account,
    get_associated_token_address,
    initialize_mint2,
    mint_to_checked,
)

MINT_SIZE = 82
DEVNET = "https://api.devnet.solana.com"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--amount", type=int, default=1000, help="whole tokens to mint")
    ap.add_argument("--decimals", type=int, default=6)
    ap.add_argument("--rpc", default=DEVNET)
    a = ap.parse_args()
    if "devnet" not in a.rpc:
        sys.exit("refusing: this script is devnet-only")

    secret = os.environ.get("SIGHTLINE_SECRET_KEY")
    if not secret:
        sys.exit("set SIGHTLINE_SECRET_KEY")
    payer = Keypair.from_base58_string(secret.strip())
    mint = Keypair()
    client = Client(a.rpc, commitment=Confirmed)
    rent = client.get_minimum_balance_for_rent_exemption(MINT_SIZE).value
    ata = get_associated_token_address(payer.pubkey(), mint.pubkey())

    ixs = [
        create_account(CreateAccountParams(from_pubkey=payer.pubkey(), to_pubkey=mint.pubkey(),
                                           lamports=rent, space=MINT_SIZE, owner=TOKEN_PROGRAM_ID)),
        initialize_mint2(InitializeMint2Params(program_id=TOKEN_PROGRAM_ID, mint=mint.pubkey(),
                                               decimals=a.decimals, mint_authority=payer.pubkey())),
        create_idempotent_associated_token_account(payer.pubkey(), payer.pubkey(), mint.pubkey()),
        mint_to_checked(MintToCheckedParams(program_id=TOKEN_PROGRAM_ID, mint=mint.pubkey(), dest=ata,
                                            mint_authority=payer.pubkey(), amount=a.amount * 10**a.decimals,
                                            decimals=a.decimals)),
    ]
    bh = client.get_latest_blockhash().value
    msg = MessageV0.try_compile(payer.pubkey(), ixs, [], bh.blockhash)
    tx = VersionedTransaction(msg, [payer, mint])
    sig = client.send_transaction(tx, opts=TxOpts(preflight_commitment=Confirmed)).value
    client.confirm_transaction(sig, Confirmed, last_valid_block_height=bh.last_valid_block_height)
    print(f"Mint:      {mint.pubkey()}")
    print(f"Minted:    {a.amount} tokens ({a.decimals} decimals) to {payer.pubkey()}")
    print(f"Signature: {sig}")
    print(f"Explorer:  https://explorer.solana.com/tx/{sig}?cluster=devnet")


if __name__ == "__main__":
    main()
