"""Sightline: a Solana transaction firewall for Hermes Agent."""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

TOOLSET = "sightline"
DEFAULT_RPC_URL = "https://api.devnet.solana.com"

STATUS_SCHEMA = {
    "name": "sightline_status",
    "description": (
        "Show the Sightline wallet status: Solana network, RPC URL and the "
        "wallet's public key. Never returns secret material."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}


def _secret(name: str) -> str | None:
    """Read a credential through Hermes' profile-aware secret route."""
    try:
        from agent.secret_scope import get_secret
    except ImportError:  # running outside Hermes (tests, scripts)
        return os.environ.get(name)
    return get_secret(name)


def _network(rpc_url: str) -> str:
    for name in ("devnet", "testnet", "mainnet"):
        if name in rpc_url:
            return name
    return "localnet" if "localhost" in rpc_url or "127.0.0.1" in rpc_url else "custom"
