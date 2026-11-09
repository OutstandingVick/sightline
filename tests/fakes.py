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

    def get_fee_for_message(self, msg, *a, **k):
        return NS(value=5000)

    def send_transaction(self, tx, opts=None):
        if self.send_errors:
            raise self.send_errors.pop(0)
        self.sent.append(tx)
        return NS(value=Signature.new_unique())

    def confirm_transaction(self, sig, *a, **k):
        if self.confirm_errors:
            raise self.confirm_errors.pop(0)
        return NS(value=[])


SYSTEM = "11111111111111111111111111111111"
FEE = 5000
ATA_RENT = 2_039_280


class FakeCluster:
    """Answers simulateTransaction by applying System transfers and SPL transfer_checked.

    lamports: {address: lamports}; tokens: {token_account: {"mint", "owner", "amount", "decimals"}}
    """

    def __init__(self, lamports=None, tokens=None):
        self.lamports = dict(lamports or {})
        self.tokens = {k: dict(v) for k, v in (tokens or {}).items()}
        self.calls = []
        self.override = None  # dict merged into the response value (to doctor results)
        self.raise_exc = None

    def __call__(self, url, body, timeout=30):
        import base64

        from solders.transaction import VersionedTransaction

        self.calls.append(body)
        if self.raise_exc:
            raise self.raise_exc
        tx = VersionedTransaction.from_bytes(base64.b64decode(body["params"][0]))
        msg = tx.message
        keys = [str(k) for k in msg.account_keys]
        lam = {k: self.lamports.get(k, 0) for k in keys}
        tok = {k: dict(v) for k, v in self.tokens.items()}
        pre_lam = dict(lam)
        pre_tok = {k: dict(v) for k, v in tok.items()}
        err, logs = None, []
        lam[keys[0]] -= FEE
        for ix in msg.instructions:
            pid = keys[ix.program_id_index]
            acc = [keys[i] for i in ix.accounts]
            data = bytes(ix.data)
            logs.append(f"Program {pid} invoke [1]")
            if pid == SYSTEM and data[:4] == (2).to_bytes(4, "little"):
                amt = int.from_bytes(data[4:12], "little")
                if lam[acc[0]] < amt:
                    err = {"InstructionError": [0, {"Custom": 1}]}
                    logs.append("Transfer: insufficient lamports")
                    break
                lam[acc[0]] -= amt
                lam[acc[1]] += amt
            elif pid.startswith("ATokenGP"):
                ata, owner, mint = acc[1], acc[2], acc[3]
                if ata not in tok:
                    lam[acc[0]] -= ATA_RENT
                    lam[ata] += ATA_RENT
                    tok[ata] = {"mint": mint, "owner": owner, "amount": 0, "decimals": None}
            elif data[:1] == bytes([12]):  # transfer_checked
                amt = int.from_bytes(data[1:9], "little")
                src, dst = acc[0], acc[2]
                if src not in tok or tok[src]["amount"] < amt:
                    err = {"InstructionError": [len(logs) - 1, {"Custom": 1}]}
                    logs.append("Program log: Error: insufficient funds")
                    break
                tok[src]["amount"] -= amt
                tok[dst]["amount"] += amt
                tok[dst]["decimals"] = data[9]
            else:
                logs.append(f"Program {pid} success")
        def tb(state):
            return [{"accountIndex": keys.index(a), "mint": t["mint"], "owner": t["owner"],
                     "uiTokenAmount": {"amount": str(t["amount"]), "decimals": t["decimals"] or 0}}
                    for a, t in state.items() if a in keys]
        watched = body["params"][1]["accounts"]["addresses"]
        value = {
            "err": err, "logs": logs, "unitsConsumed": 1500, "fee": FEE,
            "preBalances": [pre_lam[k] for k in keys],
            "postBalances": [pre_lam[k] if err else lam[k] for k in keys],
            "preTokenBalances": tb(pre_tok), "postTokenBalances": tb(pre_tok if err else tok),
            "accounts": [{"lamports": lam.get(a, 0), "space": 165 if a in tok else 0} for a in watched],
        }
        if self.override:
            value.update(self.override)
        return {"result": {"value": value}}
