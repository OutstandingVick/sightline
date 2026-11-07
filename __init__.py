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


def sightline_status(args: dict, **kwargs) -> str:
    """Return network, RPC URL and public key. The secret never leaves this function."""
    try:
        rpc_url = _secret("SIGHTLINE_RPC_URL") or DEFAULT_RPC_URL
        out = {"network": _network(rpc_url), "rpc_url": rpc_url, "public_key": None}
        secret = _secret("SIGHTLINE_SECRET_KEY")
        if not secret:
            out["error"] = "SIGHTLINE_SECRET_KEY is not set"
            return json.dumps(out)
        from solders.keypair import Keypair

        out["public_key"] = str(Keypair.from_base58_string(secret.strip()).pubkey())
        return json.dumps(out)
    except ModuleNotFoundError as exc:
        return json.dumps({"error": f"missing dependency {exc.name!r}; enable the plugin and restart Hermes"})
    except Exception as exc:  # never raise, never echo the secret
        return json.dumps({"error": f"status failed: {type(exc).__name__}"})


def _pre_tool_call(tool_name: str = "", **kwargs) -> None:
    """Placeholder firewall hook: log Sightline tool calls, allow everything."""
    if tool_name.startswith("sightline_"):
        logger.info("sightline: pre_tool_call %s", tool_name)
    return None


def register(ctx) -> None:
    ctx.register_tool(
        name="sightline_status",
        toolset=TOOLSET,
        schema=STATUS_SCHEMA,
        handler=sightline_status,
        description=STATUS_SCHEMA["description"],
    )
    ctx.register_hook("pre_tool_call", _pre_tool_call)
