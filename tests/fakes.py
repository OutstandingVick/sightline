"""A minimal fake of solana.rpc.api.Client for offline wallet tests."""

from types import SimpleNamespace as NS

from solders.hash import Hash
from solders.signature import Signature
from spl.token.constants import TOKEN_PROGRAM_ID


def mint_data(decimals: int) -> bytes:
    data = bytearray(82)
    data[44] = decimals
    return bytes(data)


class FakeClient:
    def __init__(self, lamports=2_000_000_000, mints=None, token_balance=0, token_accounts=()):
        self.lamports = lamports
        self.mints = mints or {}  # Pubkey -> decimals
        self.token_balance = token_balance
        self.token_accounts = list(token_accounts)
        self.sent = []
        self.send_errors = []  # exceptions raised by successive send_transaction calls
        self.confirm_errors = []
        self.blockhashes = 0

    def get_genesis_hash(self):
        return NS(value="EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG")

    def get_balance(self, owner, *a, **k):
        return NS(value=self.lamports)

    def get_latest_blockhash(self, *a, **k):
        self.blockhashes += 1
        return NS(value=NS(blockhash=Hash.new_unique(), last_valid_block_height=100))

    def get_account_info(self, pk, *a, **k):
        if pk in self.mints:
            return NS(value=NS(owner=TOKEN_PROGRAM_ID, data=mint_data(self.mints[pk])))
        if self.token_balance:
            return NS(value=NS(owner=TOKEN_PROGRAM_ID, data=b"\0" * 165))
        return NS(value=None)

    def get_token_account_balance(self, pk, *a, **k):
        return NS(value=NS(amount=str(self.token_balance)))

    def get_token_accounts_by_owner_json_parsed(self, owner, opts, *a, **k):
        accs = self.token_accounts if opts.program_id == TOKEN_PROGRAM_ID else []
        return NS(value=[NS(account=NS(data=NS(parsed={"info": a}))) for a in accs])

    def send_transaction(self, tx, opts=None):
        if self.send_errors:
            raise self.send_errors.pop(0)
        self.sent.append(tx)
        return NS(value=Signature.new_unique())

    def confirm_transaction(self, sig, *a, **k):
        if self.confirm_errors:
            raise self.confirm_errors.pop(0)
        return NS(value=[])
