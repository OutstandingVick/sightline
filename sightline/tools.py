"""Model-facing tools. Intent-level only: no tool accepts raw transactions or instructions."""

from __future__ import annotations

import json
import logging

# Solana deps are imported lazily so the plugin registers even before they are installed.

logger = logging.getLogger(__name__)

_NET_NOTE = "Runs on Solana devnet by default (test funds, no real value) unless the user configured another RPC."

STATUS_SCHEMA = {
    "name": "sightline_status",
    "description": (
        "Answer questions about the user's Sightline wallet setup ('what's my sightline status?'): "
        "the Solana network, RPC URL and the wallet's public address. " + _NET_NOTE
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

PAY_SCHEMA = {
    "name": "sightline_pay",
    "description": (
        "Send SOL or an SPL token from the user's Sightline wallet to a Solana address. "
        "Only call when the user clearly asked to send/pay a specific amount to a specific address. "
        "Creates the recipient's token account if needed. Returns a summary, the transaction "
        "signature and an explorer link. " + _NET_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "recipient": {"type": "string", "description": "Recipient wallet address (base58 public key)."},
            "amount": {"type": "number", "exclusiveMinimum": 0,
                       "description": "Amount in whole units of the token, e.g. 0.01 for 0.01 SOL, 1 for 1 USDC."},
            "token": {"type": "string", "default": "SOL",
                      "description": "'SOL' (default), a known symbol such as 'USDC', or an SPL mint address."},
        },
        "required": ["recipient", "amount"],
    },
}

def _wallet():
    from .config import load_settings
    from .wallet import Wallet

    return Wallet(load_settings())

def _guard(fn):
    """Tool handlers return JSON strings and never raise or leak tracebacks."""

    def handler(args: dict, **kwargs) -> str:
        try:
            return json.dumps(fn(args or {}))
        except ModuleNotFoundError as exc:
            return json.dumps({"error": "missing_dependency",
                               "message": f"{exc.name!r} not installed; enable the plugin and restart Hermes"})
        except Exception as exc:
            if hasattr(exc, "to_dict"):  # WalletError, SimulationFailed (with report)
                return json.dumps(exc.to_dict())
            if hasattr(exc, "code") and hasattr(exc, "message"):  # ConfigError
                return json.dumps({"error": exc.code, "message": exc.message})
            logger.warning("sightline: %s failed: %s", fn.__name__, type(exc).__name__)
            return json.dumps({"error": "internal_error", "message": type(exc).__name__})

    handler.__name__ = fn.__name__
    return handler

@_guard
def sightline_status(args: dict) -> dict:
    from .config import load_settings

    s = load_settings()
    return {"network": s.network, "rpc_url": s.rpc_url, "public_key": str(s.public_key)}

@_guard
def sightline_balance(args: dict) -> dict:
    w = _wallet()
    return {"network": w.settings.network, "public_key": str(w.owner), **w.get_balances()}

@_guard
def sightline_pay(args: dict) -> dict:
    from .intents import execute_intent, pay_intent

    w = _wallet()
    intent = pay_intent(w, args.get("recipient", ""), args.get("amount"), args.get("token") or "SOL")
    return execute_intent(w, intent).to_dict()

TOOLS = [
    (STATUS_SCHEMA, sightline_status),
    (BALANCE_SCHEMA, sightline_balance),
    (PAY_SCHEMA, sightline_pay),
]
