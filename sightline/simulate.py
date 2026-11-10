"""Simulation.

Run ``simulateTransaction`` on an unsigned built transaction and turn the result into a
``SimulationReport``: success/error, logs, compute units, fee, our SOL and token deltas,
programs invoked, writable accounts and any accounts it creates.

How balance changes are computed (and why):
    The cluster's simulateTransaction response carries ``preBalances``/``postBalances`` and
    ``preTokenBalances``/``postTokenBalances`` (verified on devnet, RPC 4.4). These are the
    runtime's own numbers for every account in the message, taken atomically from one
    simulation, so we use them directly instead of fetching "pre" state separately (which can
    race with other transactions) and decoding post-state bytes ourselves. solana-py's typed
    ``SimulateTransactionResp`` drops these fields, so we call the RPC as raw JSON. If an RPC
    omits them we fail closed rather than guess.

    The ``accounts`` config (base64) is still requested for the watched accounts: their
    post-state ``space`` tells us whether a zero-balance account was *created* with data
    (e.g. a recipient token account) versus a plain SOL recipient getting funded.
"""

from __future__ import annotations

import base64
import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal

import httpx
from solders.message import MessageV0

from .amounts import from_base_units
from .tokens import short, symbol_for

MAX_LOGS = 30
MAX_LOG_CHARS = 300

PROGRAM_NAMES = {
    "11111111111111111111111111111111": "System",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "Token",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb": "Token-2022",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL": "Associated Token",
    "ComputeBudget111111111111111111111111111111": "Compute Budget",
    "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr": "Memo",
    "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo": "Memo",
}


def program_label(program_id: str) -> str:
    return PROGRAM_NAMES.get(program_id, f"unknown {short(program_id)}")


@dataclass
class TokenDelta:
    mint: str
    symbol: str
    delta_ui: str  # signed Decimal as string, exact
    decimals: int
    pre_ui: str = "0"  # our balance of this mint before the tx


@dataclass
class SimulationReport:
    ok: bool
    error: str | None = None
    logs: list[str] = field(default_factory=list)
    compute_units: int | None = None
    fee_lamports: int = 0
    sol_delta_lamports: int = 0  # our wallet, fee included
    token_deltas: list[TokenDelta] = field(default_factory=list)  # our wallet
    programs: list[str] = field(default_factory=list)  # program ids, in order of first use
    unknown_programs: list[str] = field(default_factory=list)
    writable_accounts: list[str] = field(default_factory=list)
    creates_accounts: bool = False
    created_accounts: list[str] = field(default_factory=list)
    rent_lamports: int = 0  # lamports moved into newly created accounts
    recipient_received: str | None = None  # what the intent's recipient gains (UI units)
    slot: int | None = None  # slot the simulation ran against
    sol_post_lamports: int | None = None  # our SOL balance after the tx
    instructions: list[str] = field(default_factory=list)  # decoded top-level kinds, e.g. "Token.TransferChecked"
    error_code: str | None = None  # stable code for `error` (see messages.NEXT_STEP)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SimulationReport":
        """Inverse of to_dict, for the audit log and firewall (Phase 4)."""
        data = dict(data)
        data["token_deltas"] = [TokenDelta(**t) for t in data.get("token_deltas") or []]
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def token_delta(self, mint: str) -> Decimal:
        return sum((Decimal(t.delta_ui) for t in self.token_deltas if t.mint == mint), Decimal(0))


def message_programs(msg: MessageV0) -> list[str]:
    keys = msg.account_keys
    seen: list[str] = []
    for ix in msg.instructions:
        pid = str(keys[ix.program_id_index])
        if pid not in seen:
            seen.append(pid)
    return seen


_SYSTEM_IX = {0: "CreateAccount", 1: "Assign", 2: "Transfer", 3: "CreateAccountWithSeed",
              4: "AdvanceNonceAccount", 5: "WithdrawNonceAccount", 6: "InitializeNonceAccount",
              7: "AuthorizeNonceAccount", 8: "Allocate", 9: "AllocateWithSeed", 10: "AssignWithSeed",
              11: "TransferWithSeed", 12: "UpgradeNonceAccount"}
_TOKEN_IX = {0: "InitializeMint", 1: "InitializeAccount", 2: "InitializeMultisig", 3: "Transfer",
             4: "Approve", 5: "Revoke", 6: "SetAuthority", 7: "MintTo", 8: "Burn", 9: "CloseAccount",
             10: "FreezeAccount", 11: "ThawAccount", 12: "TransferChecked", 13: "ApproveChecked",
             14: "MintToChecked", 15: "BurnChecked", 16: "InitializeAccount2", 17: "SyncNative",
             18: "InitializeAccount3", 20: "InitializeMint2"}
_ATA_IX = {0: "Create", 1: "CreateIdempotent", 2: "RecoverNested"}
_CB_IX = {0: "RequestUnits", 1: "RequestHeapFrame", 2: "SetComputeUnitLimit", 3: "SetComputeUnitPrice",
          4: "SetLoadedAccountsDataSizeLimit"}


def decode_instruction(program_id: str, data: bytes) -> str:
    """Name a top-level instruction as "<Program>.<Kind>" (Unknown when it can't be decoded)."""
    name = PROGRAM_NAMES.get(program_id)
    if name is None:
        return f"unknown {short(program_id)}"
    if name == "System":
        kind = _SYSTEM_IX.get(int.from_bytes(data[:4], "little")) if len(data) >= 4 else None
    elif name in ("Token", "Token-2022"):
        kind = _TOKEN_IX.get(data[0]) if data else None
    elif name == "Associated Token":
        kind = _ATA_IX.get(data[0] if data else 0)
    elif name == "Compute Budget":
        kind = _CB_IX.get(data[0]) if data else None
    else:  # Memo
        kind = "Memo"
    return f"{name}.{kind or 'Unknown'}"


def instruction_kinds(msg: MessageV0) -> list[str]:
    keys = msg.account_keys
    return [decode_instruction(str(keys[ix.program_id_index]), bytes(ix.data)) for ix in msg.instructions]


def message_writable(msg: MessageV0) -> list[str]:
    h = msg.header
    keys = [str(k) for k in msg.account_keys]
    n_sig = h.num_required_signatures
    signed = keys[: n_sig - h.num_readonly_signed_accounts]
    unsigned = keys[n_sig: len(keys) - h.num_readonly_unsigned_accounts]
    return signed + unsigned


def _post(url: str, body: dict, timeout: float = 30) -> dict:
    """JSON-RPC POST. Separate so tests can replace it."""
    resp = httpx.post(url, json=body, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _rpc_simulate(url: str, tx_bytes: bytes, addresses: list[str]) -> dict:
    body = {
        "jsonrpc": "2.0", "id": 1, "method": "simulateTransaction",
        "params": [base64.b64encode(tx_bytes).decode(), {
            "encoding": "base64",
            "sigVerify": False,
            "replaceRecentBlockhash": True,
            "commitment": "confirmed",
            "accounts": {"encoding": "base64", "addresses": addresses},
        }],
    }
    out = _post(url, body)
    if "error" in out:
        raise RuntimeError(f"RPC error {out['error'].get('code')}: {out['error'].get('message')}")
    result = out["result"]
    value = dict(result["value"])
    value["_slot"] = (result.get("context") or {}).get("slot")
    return value


def _fee_for_message(wallet, msg: MessageV0) -> int | None:
    try:
        return wallet.client.get_fee_for_message(msg).value
    except Exception:
        return None


def _token_map(entries: list[dict] | None) -> dict[int, dict]:
    return {e["accountIndex"]: e for e in entries or []}


def simulate(wallet, built, recipient: str | None = None) -> SimulationReport:
    """Simulate ``built`` (unsigned). Never raises: RPC failures become ok=False (fail closed)."""
    msg: MessageV0 = built.tx.message
    keys = [str(k) for k in msg.account_keys]
    owner = str(wallet.owner)
    programs = message_programs(msg)
    report = SimulationReport(
        ok=False,
        programs=programs,
        unknown_programs=[p for p in programs if p not in PROGRAM_NAMES],
        writable_accounts=message_writable(msg),
        instructions=instruction_kinds(msg),
    )
    watched = list(dict.fromkeys([owner, *getattr(built, "watch", []), *report.writable_accounts]))
    try:
        value = _rpc_simulate(wallet.settings.rpc_url, bytes(built.tx), watched)
    except Exception as exc:  # timeouts, HTTP errors, malformed responses
        timeout = "timeout" in type(exc).__name__.lower() or "timed out" in str(exc).lower()
        report.error_code = "rpc_timeout" if timeout else "rpc_error"
        detail = re.sub(r"\?\S*", "", str(exc))[:160]  # drop query strings (RPC URLs can carry API keys)
        report.error = "the Solana RPC timed out" if timeout else f"the Solana RPC failed: {detail}"
        return report

    report.logs = [line[:MAX_LOG_CHARS] for line in (value.get("logs") or [])[-MAX_LOGS:]]
    report.compute_units = value.get("unitsConsumed")
    report.slot = value.get("_slot")
    fee = _fee_for_message(wallet, msg)
    report.fee_lamports = fee if fee is not None else int(value.get("fee") or 0)

    if value.get("err") is not None:
        report.error_code, report.error = _describe_err(value["err"], report.logs)
        return report

    pre, post = value.get("preBalances"), value.get("postBalances")
    fields = ("preBalances", "postBalances", "preTokenBalances", "postTokenBalances")
    if any(value.get(f) is None for f in fields) or len(pre) != len(keys) or len(post) != len(keys):
        report.error = "RPC did not return balance changes; refusing to proceed"
        report.error_code = "rpc_error"
        return report

    report.sol_delta_lamports = post[0] - pre[0] if keys and keys[0] == owner else _delta(keys, pre, post, owner)
    report.sol_post_lamports = post[keys.index(owner)] if owner in keys else None

    # Accounts that went from 0 lamports to funded *with data* were created by this tx.
    spaces = {addr: (acc or {}).get("space", 0) for addr, acc in zip(watched, value.get("accounts") or [])}
    for i, addr in enumerate(keys):
        if i < len(pre) and pre[i] == 0 and post[i] > 0 and spaces.get(addr, 0) > 0:
            report.created_accounts.append(addr)
            report.rent_lamports += post[i]
    report.creates_accounts = bool(report.created_accounts)

    pre_t, post_t = _token_map(value["preTokenBalances"]), _token_map(value["postTokenBalances"])
    by_mint: dict[str, list] = {}
    received: Decimal | None = None
    for idx in sorted(set(pre_t) | set(post_t)):
        entry = post_t.get(idx) or pre_t[idx]
        decimals = entry["uiTokenAmount"]["decimals"]
        before = int(pre_t[idx]["uiTokenAmount"]["amount"]) if idx in pre_t else 0
        after = int(post_t[idx]["uiTokenAmount"]["amount"]) if idx in post_t else 0
        delta = from_base_units(after - before, decimals)
        if entry.get("owner") == owner and after != before:
            slot = by_mint.setdefault(entry["mint"], [Decimal(0), decimals, Decimal(0)])
            slot[0] += delta
            slot[2] += from_base_units(before, decimals)
        if recipient and entry.get("owner") == recipient:
            received = (received or Decimal(0)) + delta
    network = wallet.settings.network
    report.token_deltas = [
        TokenDelta(mint=m, symbol=symbol_for(m, network) or short(m),
                   delta_ui=_fmt(d), decimals=dec, pre_ui=_fmt(pre_amt))
        for m, (d, dec, pre_amt) in by_mint.items()
    ]
    if recipient and received is None and recipient in keys:
        i = keys.index(recipient)
        received = from_base_units(post[i] - pre[i], 9)
    report.recipient_received = _fmt(received) if received is not None else None
    report.ok = True
    return report


def _delta(keys: list[str], pre: list[int], post: list[int], addr: str) -> int:
    i = keys.index(addr) if addr in keys else -1
    return post[i] - pre[i] if i >= 0 else 0


def _fmt(d: Decimal) -> str:
    return format(d.normalize(), "f") if d != 0 else "0"


def _describe_err(err, logs: list[str]) -> tuple[str, str]:
    """(code, text) for a simulation error."""
    text = " ".join(logs).lower()
    if "insufficient lamports" in text:
        return "insufficient_funds", "insufficient funds"
    if err == "AccountNotFound":
        return "empty_wallet", "insufficient funds: the wallet has no SOL to pay fees"
    if isinstance(err, dict) and "InstructionError" in err:
        idx, detail = err["InstructionError"]
        if detail == {"Custom": 1}:  # the Token program's InsufficientFunds
            return "insufficient_token", f"insufficient token balance (instruction {idx})"
        return "simulation_failed", f"instruction {idx} failed: {detail}"
    if "insufficient funds" in text:
        return "insufficient_funds", "insufficient funds"
    if err == "BlockhashNotFound":
        return "blockhash_expired", "the blockhash expired before simulation"
    return "simulation_failed", f"simulation failed: {err}"
