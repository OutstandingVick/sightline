"""Configuration.

Resolves SIGHTLINE_SECRET_KEY / SIGHTLINE_RPC_URL / SIGHTLINE_ALLOW_MAINNET through
Hermes' profile-aware secret route, derives the cluster from the RPC URL, and refuses
mainnet unless explicitly allowed. The keypair is held here but never logged, repr'd
or returned.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import quote

from solders.keypair import Keypair
from solders.pubkey import Pubkey

DEFAULT_RPC_URL = "https://api.devnet.solana.com"
MAINNET_GENESIS_HASH = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"


class ConfigError(Exception):
    """Raised for missing/invalid configuration. Messages never contain secrets."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def read_env(name: str) -> str | None:
    """Read a credential through Hermes' secret route, or os.environ outside Hermes."""
    try:
        from agent.secret_scope import get_secret
    except ImportError:  # tests, scripts
        value = os.environ.get(name)
    else:
        value = get_secret(name)
    value = value.strip() if isinstance(value, str) else None
    return value or None


def network_from_url(rpc_url: str) -> str:
    """devnet / testnet / mainnet from well-known RPC hostnames, else "custom"."""
    url = rpc_url.lower()
    if "devnet" in url:
        return "devnet"
    if "testnet" in url:
        return "testnet"
    if "mainnet" in url:
        return "mainnet"
    return "custom"


def _truthy(value: str | None) -> bool:
    return (value or "").lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    rpc_url: str
    network: str
    allow_mainnet: bool
    keypair: Keypair = field(repr=False, compare=False)

    @property
    def public_key(self) -> Pubkey:
        return self.keypair.pubkey()

    def explorer_url(self, signature: str) -> str:
        base = f"https://explorer.solana.com/tx/{signature}"
        if self.network == "mainnet":
            return base
        if self.network in ("devnet", "testnet"):
            return f"{base}?cluster={self.network}"
        return f"{base}?cluster=custom&customUrl={quote(self.rpc_url, safe='')}"

    def check_genesis(self, genesis_hash: str) -> None:
        """Refuse a custom RPC that turns out to be mainnet (unless allowed)."""
        if genesis_hash == MAINNET_GENESIS_HASH and not self.allow_mainnet:
            raise ConfigError("mainnet_refused", "RPC points at mainnet; set SIGHTLINE_ALLOW_MAINNET=1 to allow it")


def load_settings() -> Settings:
    rpc_url = read_env("SIGHTLINE_RPC_URL") or DEFAULT_RPC_URL
    network = network_from_url(rpc_url)
    allow_mainnet = _truthy(read_env("SIGHTLINE_ALLOW_MAINNET"))
    if network == "mainnet" and not allow_mainnet:
        raise ConfigError("mainnet_refused", "mainnet is disabled; set SIGHTLINE_ALLOW_MAINNET=1 to allow it")
    secret = read_env("SIGHTLINE_SECRET_KEY")
    if not secret:
        raise ConfigError("missing_secret", "SIGHTLINE_SECRET_KEY is not set")
    try:
        keypair = Keypair.from_base58_string(secret)
    except Exception:
        raise ConfigError("invalid_secret", "SIGHTLINE_SECRET_KEY is not a valid base58 keypair") from None
    return Settings(rpc_url=rpc_url, network=network, allow_mainnet=allow_mainnet, keypair=keypair)
