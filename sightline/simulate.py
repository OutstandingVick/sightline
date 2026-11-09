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
from dataclasses import asdict, dataclass, field
from decimal import Decimal

import httpx
from solders.message import MessageV0

from .amounts import from_base_units
from .tokens import short, symbol_for

MAX_LOGS = 30

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

    def to_dict(self) -> dict:
        return asdict(self)

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
    return out["result"]["value"]


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
    )
    watched = list(dict.fromkeys([owner, *getattr(built, "watch", []), *report.writable_accounts]))
    try:
        value = _rpc_simulate(wallet.settings.rpc_url, bytes(built.tx), watched)
    except Exception as exc:  # timeouts, HTTP errors, malformed responses
        report.error = f"simulation RPC failed: {type(exc).__name__}: {str(exc)[:200]}"
        return report

    report.logs = (value.get("logs") or [])[-MAX_LOGS:]
    report.compute_units = value.get("unitsConsumed")
    fee = _fee_for_message(wallet, msg)
    report.fee_lamports = fee if fee is not None else int(value.get("fee") or 0)

    if value.get("err") is not None:
        report.error = _describe_err(value["err"], report.logs)
        return report

    pre, post = value.get("preBalances"), value.get("postBalances")
    fields = ("preBalances", "postBalances", "preTokenBalances", "postTokenBalances")
    if any(value.get(f) is None for f in fields) or len(pre) != len(keys) or len(post) != len(keys):
        report.error = "RPC did not return balance changes; refusing to proceed"
        return report

    report.sol_delta_lamports = post[0] - pre[0] if keys and keys[0] == owner else _delta(keys, pre, post, owner)

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
            slot = by_mint.setdefault(entry["mint"], [Decimal(0), decimals])
            slot[0] += delta
        if recipient and entry.get("owner") == recipient:
            received = (received or Decimal(0)) + delta
    network = wallet.settings.network
    report.token_deltas = [
        TokenDelta(mint=m, symbol=symbol_for(m, network) or short(m),
                   delta_ui=_fmt(d), decimals=dec)
        for m, (d, dec) in by_mint.items()
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


def _describe_err(err, logs: list[str]) -> str:
    text = " ".join(logs).lower()
    if "insufficient lamports" in text or "insufficient funds" in text:
        return "insufficient funds"
    if err == "AccountNotFound":
        return "insufficient funds: the wallet has no SOL to pay fees"
    if isinstance(err, dict) and "InstructionError" in err:
        idx, detail = err["InstructionError"]
        if detail == {"Custom": 1}:
            return f"insufficient token balance (instruction {idx})"
        return f"instruction {idx} failed: {detail}"
    return f"simulation failed: {err}"
