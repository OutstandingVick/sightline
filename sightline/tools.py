"""Model-facing tools. Intent-level only: no tool accepts raw transactions or instructions."""

from __future__ import annotations

import json
import logging

from .messages import error_dict

# Solana deps are imported lazily so the plugin registers even before they are installed.

logger = logging.getLogger(__name__)

_NET_NOTE = "Runs on Solana devnet by default (test funds, no real value) unless the user configured another RPC."

STATUS_SCHEMA = {
    "name": "sightline_status",
    "description": (
        "Answer questions about the user's Sightline wallet setup ('what's my sightline status?'): "
        "the Solana network, RPC URL, the wallet's public address and the user's spending grants "
        "(read-only: grants can only be created or revoked by the user). " + _NET_NOTE
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

BALANCE_SCHEMA = {
    "name": "sightline_balance",
    "description": (
        "Get the user's Sightline wallet balances: SOL plus every SPL token it holds "
        "(symbol when known, otherwise a shortened mint address). Use for 'what's my balance?', "
        "'how much USDC do I have?'. " + _NET_NOTE
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

_PAY_PARAMS = {
    "type": "object",
    "properties": {
        "recipient": {"type": "string", "description": "Recipient wallet address (base58 public key)."},
        "amount": {"type": "number", "exclusiveMinimum": 0,
                   "description": "Amount in whole units of the token, e.g. 0.01 for 0.01 SOL, 1 for 1 USDC."},
        "token": {"type": "string", "default": "SOL",
                  "description": "'SOL' (default), a known symbol such as 'USDC', or an SPL mint address."},
    },
    "required": ["recipient", "amount"],
}

PREVIEW_SCHEMA = {
    "name": "sightline_preview",
    "description": (
        "Dry-run a payment from the user's Sightline wallet: builds and simulates it and explains in "
        "plain English what would happen (amount, fee, accounts created, programs), WITHOUT signing or "
        "sending. Use for 'preview sending…', 'what would happen if I send…'. " + _NET_NOTE
    ),
    "parameters": _PAY_PARAMS,
}

PAY_SCHEMA = {
    "name": "sightline_pay",
    "description": (
        "Send SOL or an SPL token from the user's Sightline wallet to a Solana address. "
        "Only call when the user clearly asked to send/pay a specific amount to a specific address. "
        "Simulates first and sends nothing if simulation fails. Payments inside one of the user's grants go "
        "through; anything else needs the user's approval or is blocked by the Sightline firewall. Creates the recipient's token account if needed. Returns a plain-English summary, the transaction "
        "signature and an explorer link. " + _NET_NOTE
    ),
    "parameters": _PAY_PARAMS,
}

def _wallet():
    from .config import load_settings
    from .wallet import Wallet

    return Wallet(load_settings())

def _guard(fn):
    """Tool handlers return JSON strings and never raise or leak tracebacks."""

    def handler(args: dict, **kwargs) -> str:
        try:
            return json.dumps(fn(args or {}, session_id=str(kwargs.get("session_id") or "")))
        except ModuleNotFoundError as exc:
            return json.dumps(error_dict("missing_dependency", f"Python package {exc.name!r} is not installed."))
        except Exception as exc:
            if hasattr(exc, "to_dict"):  # WalletError, SimulationFailed (with report)
                return json.dumps(exc.to_dict())
            if hasattr(exc, "code") and hasattr(exc, "message"):  # ConfigError
                return json.dumps(error_dict(exc.code, exc.message))
            logger.warning("sightline: %s failed: %s", fn.__name__, type(exc).__name__)
            return json.dumps(error_dict("internal_error", f"Unexpected error ({type(exc).__name__})."))

    handler.__name__ = fn.__name__
    return handler

@_guard
def sightline_status(args: dict, session_id: str = "") -> dict:
    from .config import load_settings

    s = load_settings()
    return {"network": s.network, "rpc_url": s.rpc_url, "public_key": str(s.public_key),
            "grants": _grant_summaries(s.network),
            "note": "Grants are read-only here; only the user can create or revoke them with /sightline."}


def _grant_summaries(network: str) -> list[dict]:
    import time

    from . import grants

    now = time.time()
    out = []
    for g in grants.list_grants():
        status = g.status(now)
        if status != "active" and now - (g.revoked_at or g.expires_at) > 24 * 3600:
            continue
        out.append({"id": g.id, "status": status, "network": g.network, "token": g.symbol,
                    "max_per_tx": g.max_per_tx, "daily_cap": g.daily_cap,
                    "remaining_24h": str(grants.remaining(g, now=now)) if status == "active" else "0",
                    "recipients": g.recipients, "expires_in_s": max(0, int(g.expires_at - now))})
    return out


@_guard
def sightline_balance(args: dict, session_id: str = "") -> dict:
    w = _wallet()
    return {"network": w.settings.network, "public_key": str(w.owner), **w.get_balances()}

@_guard
def sightline_pay(args: dict, session_id: str = "") -> dict:
    from .gate import cache_key, take
    from .intents import execute_intent, pay_intent

    evaluation = take(cache_key(args, session_id))  # the firewall hook's verdict for this exact call
    w = _wallet()
    intent = pay_intent(w, args.get("recipient", ""), args.get("amount"), args.get("token") or "SOL")
    return execute_intent(w, intent, evaluation=evaluation).to_dict()

@_guard
def sightline_preview(args: dict, session_id: str = "") -> dict:
    from .intents import pay_intent, preview_intent

    w = _wallet()
    intent = pay_intent(w, args.get("recipient", ""), args.get("amount"), args.get("token") or "SOL")
    return preview_intent(w, intent).to_dict()


TOOLS = [
    (STATUS_SCHEMA, sightline_status),
    (BALANCE_SCHEMA, sightline_balance),
    (PREVIEW_SCHEMA, sightline_preview),
    (PAY_SCHEMA, sightline_pay),
]
