"""Wallet.

Read balances, build unsigned transfers, and sign + send. Build and send are separate
on purpose: Phase 2 inserts simulation between them and Phase 4 the firewall. The
keypair is only used inside ``sign_and_send``; nothing here returns secret material.

All transactions are v0 ``VersionedTransaction``s.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal

import httpx
from solana.exceptions import SolanaRpcException
from solana.rpc.api import Client
from solana.rpc.commitment import Confirmed
from solana.rpc.core import RPCException, TransactionExpiredBlockheightExceededError, UnconfirmedTxError
from solana.rpc.types import TokenAccountOpts, TxOpts
from solders.hash import Hash
from solders.instruction import Instruction
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.system_program import TransferParams, transfer
from solders.transaction import VersionedTransaction
from spl.token.constants import TOKEN_2022_PROGRAM_ID, TOKEN_PROGRAM_ID
from spl.token.instructions import (
    TransferCheckedParams,
    create_idempotent_associated_token_account,
    get_associated_token_address,
    transfer_checked,
)

from .amounts import SOL_DECIMALS, AmountError, from_base_units, to_base_units
from .config import ConfigError, Settings
from .tokens import AddressError, parse_address, short, symbol_for

logger = logging.getLogger(__name__)

MINT_DECIMALS_OFFSET = 44  # SPL Mint layout: authority option(36) + supply(8) → decimals


class WalletError(Exception):
    """A user-presentable failure with a stable code. Never carries tracebacks."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict:
        return {"error": self.code, "message": self.message}


@dataclass
class BuiltTx:
    """An unsigned transaction plus what is needed to explain or rebuild it."""

    tx: VersionedTransaction
    instructions: list[Instruction]
    last_valid_block_height: int
    summary: str
    watch: list[str] = field(default_factory=list)  # accounts simulation should report on


@dataclass
class Mint:
    address: Pubkey
    decimals: int
    program_id: Pubkey


class Wallet:
    def __init__(self, settings: Settings, client: Client | None = None):
        self.settings = settings
        self.client = client or Client(settings.rpc_url, commitment=Confirmed, timeout=30)
        self._genesis_checked = settings.network != "custom"

    @property
    def owner(self) -> Pubkey:
        return self.settings.public_key

    # -- guards ------------------------------------------------------------

    def _check_cluster(self) -> None:
        if self._genesis_checked:
            return
        genesis = str(self._rpc(self.client.get_genesis_hash).value)
        try:
            self.settings.check_genesis(genesis)
        except ConfigError as exc:
            raise WalletError(exc.code, exc.message) from None
        self._genesis_checked = True

    def _rpc(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (httpx.TimeoutException, TimeoutError):
            raise WalletError("rpc_timeout", "the Solana RPC timed out; try again") from None
        except (SolanaRpcException, httpx.HTTPError, RPCException) as exc:
            raise WalletError("rpc_error", f"RPC request failed: {_brief(exc)}") from None

    # -- reads ---------------------------------------------------------------

    def get_balances(self) -> dict:
        self._check_cluster()
        lamports = self._rpc(self.client.get_balance, self.owner).value
        tokens = []
        for program in (TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID):
            resp = self._rpc(
                self.client.get_token_accounts_by_owner_json_parsed,
                self.owner, TokenAccountOpts(program_id=program),
            )
            for acc in resp.value:
                info = acc.account.data.parsed["info"]
                amt = info["tokenAmount"]
                mint = info["mint"]
                tokens.append({
                    "mint": mint,
                    "symbol": symbol_for(mint, self.settings.network) or short(mint),
                    "amount": str(from_base_units(int(amt["amount"]), amt["decimals"]).normalize()),
                    "decimals": amt["decimals"],
                })
        tokens.sort(key=lambda t: t["symbol"])
        return {
            "sol": str(from_base_units(lamports, SOL_DECIMALS).normalize()),
            "lamports": lamports,
            "tokens": tokens,
        }

    def get_mint(self, mint: Pubkey) -> Mint:
        info = self._rpc(self.client.get_account_info, mint).value
        if info is None:
            raise WalletError("unknown_mint", f"mint {mint} does not exist on {self.settings.network}")
        if info.owner not in (TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID) or len(info.data) <= MINT_DECIMALS_OFFSET:
            raise WalletError("unknown_mint", f"{mint} is not an SPL token mint")
        return Mint(address=mint, decimals=info.data[MINT_DECIMALS_OFFSET], program_id=info.owner)

    # -- builds --------------------------------------------------------------

    def _blockhash(self) -> tuple[Hash, int]:
        value = self._rpc(self.client.get_latest_blockhash, Confirmed).value
        return value.blockhash, value.last_valid_block_height

    def _compile(self, instructions: list[Instruction], summary: str, watch: list[str] | None = None) -> BuiltTx:
        blockhash, last_valid = self._blockhash()
        msg = MessageV0.try_compile(self.owner, instructions, [], blockhash)
        tx = VersionedTransaction.populate(msg, [Signature.default()])
        return BuiltTx(tx=tx, instructions=instructions, last_valid_block_height=last_valid,
                       summary=summary, watch=list(watch or []))

    def build_sol_transfer(self, to: str, amount_sol) -> BuiltTx:
        self._check_cluster()
        dest = _address(to, "recipient")
        lamports = _units(amount_sol, SOL_DECIMALS)
        # Balance is not pre-checked here: simulation is the single gate (Phase 2).
        ix = transfer(TransferParams(from_pubkey=self.owner, to_pubkey=dest, lamports=lamports))
        return self._compile([ix], f"send {from_base_units(lamports, 9).normalize()} SOL to {dest}",
                             watch=[str(self.owner), str(dest)])

    def build_spl_transfer(self, to: str, mint: str | Pubkey, amount) -> BuiltTx:
        self._check_cluster()
        dest_owner = _address(to, "recipient")
        mint_pk = mint if isinstance(mint, Pubkey) else _address(mint, "mint")
        m = self.get_mint(mint_pk)
        units = _units(amount, m.decimals)
        label = symbol_for(str(mint_pk), self.settings.network) or short(str(mint_pk))
        source = get_associated_token_address(self.owner, mint_pk, m.program_id)
        dest = get_associated_token_address(dest_owner, mint_pk, m.program_id)
        ixs = [
            create_idempotent_associated_token_account(self.owner, dest_owner, mint_pk, m.program_id),
            transfer_checked(TransferCheckedParams(
                program_id=m.program_id, source=source, mint=mint_pk, dest=dest,
                owner=self.owner, amount=units, decimals=m.decimals,
            )),
        ]
        return self._compile(ixs, f"send {from_base_units(units, m.decimals).normalize()} {label} to {dest_owner}",
                             watch=[str(self.owner), str(source), str(dest_owner), str(dest)])

    # -- send ----------------------------------------------------------------

    def _rebuild(self, built: BuiltTx) -> BuiltTx:
        return self._compile(built.instructions, built.summary, built.watch)

    def sign_and_send(self, built: BuiltTx) -> str:
        """Sign with the wallet keypair, send, confirm at "confirmed". Returns the signature.

        If the blockhash expires before confirmation, rebuild with a fresh one and retry once.
        """
        self._check_cluster()
        for attempt in (1, 2):
            tx = VersionedTransaction(built.tx.message, [self.settings.keypair])
            try:
                sig = self.client.send_transaction(tx, opts=TxOpts(preflight_commitment=Confirmed)).value
                self.client.confirm_transaction(sig, Confirmed, last_valid_block_height=built.last_valid_block_height)
                return str(sig)
            except TransactionExpiredBlockheightExceededError:
                if attempt == 2:
                    raise WalletError("blockhash_expired", "transaction expired twice; try again") from None
                logger.info("sightline: blockhash expired, rebuilding")
                built = self._rebuild(built)
            except UnconfirmedTxError:
                raise WalletError("unconfirmed", "sent but not confirmed in time; check the explorer") from None
            except (httpx.TimeoutException, TimeoutError):
                raise WalletError("rpc_timeout", "the Solana RPC timed out while sending") from None
            except (RPCException, SolanaRpcException, httpx.HTTPError) as exc:
                text = _brief(exc)
                if "Blockhash not found" in text and attempt == 1:
                    built = self._rebuild(built)
                    continue
                raise _send_error(text) from None
        raise WalletError("send_failed", "could not send the transaction")


def _address(value: str, what: str) -> Pubkey:
    try:
        return parse_address(value, what)
    except AddressError as exc:
        raise WalletError("invalid_address", str(exc)) from None


def _units(amount, decimals: int) -> int:
    try:
        return to_base_units(amount, decimals)
    except AmountError as exc:
        raise WalletError("invalid_amount", str(exc)) from None


def _brief(exc: Exception) -> str:
    text = str(exc.args[0] if getattr(exc, "args", None) else exc)
    return text[:300]


def _send_error(text: str) -> WalletError:
    low = text.lower()
    if "insufficient lamports" in low or "insufficient funds" in low or "custom program error: 0x1" in low:
        return WalletError("insufficient_funds", "insufficient funds for this transfer and its fees")
    if "accountnotfound" in low.replace(" ", "") or "attempt to debit an account" in low:
        return WalletError("insufficient_funds", "the wallet has no SOL to pay fees")
    return WalletError("send_failed", f"transaction rejected: {text}")
