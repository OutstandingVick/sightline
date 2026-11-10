"""First-run setup: a devnet wallet, stored the Hermes way, funded from the faucet.

Used by ``/sightline setup`` (inside Hermes) and ``scripts/setup_devnet.py``.

- Keeps an existing valid SIGHTLINE_SECRET_KEY (never overwrites one); refuses to
  touch an invalid one and says how to fix it.
- Otherwise generates a keypair and saves it to Hermes' .env through
  ``hermes_cli.config.save_env_value`` (outside Hermes: ``$HERMES_HOME/.env``).
- Requests devnet SOL with retry and backoff; if the faucet rate-limits, prints the
  address and the web faucets to use instead.
- Never prints or returns the secret.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from .config import DEFAULT_RPC_URL, ConfigError, network_from_url, parse_secret, read_env
from .messages import FAUCET_URLS

LAMPORTS_PER_SOL = 1_000_000_000
AIRDROP_LAMPORTS = LAMPORTS_PER_SOL  # 1 SOL
FUNDED_LAMPORTS = 100_000_000  # 0.1 SOL is plenty for testing
BACKOFF_S = (2, 5, 10)


def _env_path() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes") / ".env"


def store_secret(secret: str) -> str:
    """Save SIGHTLINE_SECRET_KEY the Hermes way. Returns where it went."""
    try:
        from hermes_cli.config import get_env_path, save_env_value
    except ImportError:
        path = _env_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = path.read_text().splitlines() if path.exists() else []
        lines = [line for line in lines if not line.lstrip().removeprefix("export ").startswith("SIGHTLINE_SECRET_KEY=")]
        lines.append(f"SIGHTLINE_SECRET_KEY={secret}")
        path.write_text("\n".join(lines) + "\n")
        path.chmod(0o600)
    else:
        save_env_value("SIGHTLINE_SECRET_KEY", secret)
        path = get_env_path()
    os.environ["SIGHTLINE_SECRET_KEY"] = secret  # this process sees it at once
    return str(path)


def _is_rate_limit(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(s in text for s in ("429", "rate", "limit", "too many", "faucet has run dry", "airdrop request failed"))


def request_airdrop(client, pubkey, lamports: int = AIRDROP_LAMPORTS, sleep=time.sleep) -> tuple[bool, str]:
    """(funded, note). Retries with backoff; confirms by reading the balance."""
    last = ""
    for attempt, wait in enumerate((0, *BACKOFF_S)):
        if wait:
            sleep(wait)
        try:
            client.request_airdrop(pubkey, lamports)
        except Exception as exc:
            last = "rate limited" if _is_rate_limit(exc) else f"{type(exc).__name__}"
            continue
        for _ in range(20):
            try:
                if client.get_balance(pubkey).value > 0:
                    return True, f"airdrop arrived (attempt {attempt + 1})"
            except Exception:
                pass
            sleep(1)
        last = "airdrop not confirmed in time"
    return False, last


def run(airdrop: bool = True, client=None, sleep=time.sleep) -> list[str]:
    """Do the setup and return the lines to show the user."""
    out: list[str] = []
    rpc_url = read_env("SIGHTLINE_RPC_URL") or DEFAULT_RPC_URL
    network = network_from_url(rpc_url)

    existing = read_env("SIGHTLINE_SECRET_KEY")
    if existing:
        try:
            keypair = parse_secret(existing)
        except ConfigError as exc:
            return [f"✗ {exc.message}",
                    "Not changing it. Fix or remove SIGHTLINE_SECRET_KEY in ~/.hermes/.env, then run setup again."]
        out.append(f"✓ Wallet already configured: {keypair.pubkey()}")
    else:
        from solders.keypair import Keypair

        keypair = Keypair()
        where = store_secret(str(keypair))
        out.append(f"✓ Created a new {network} wallet: {keypair.pubkey()}")
        out.append(f"  Secret key saved to {where} as SIGHTLINE_SECRET_KEY (not shown here).")

    if network not in ("devnet", "testnet"):
        out.append(f"Network is {network.upper()}: no faucet. Fund {keypair.pubkey()} yourself.")
        return out
    if not airdrop:
        return out

    if client is None:
        from solana.rpc.api import Client

        client = Client(rpc_url, timeout=20)
    try:
        balance = client.get_balance(keypair.pubkey()).value
    except Exception as exc:
        out.append(f"✗ Could not reach the Solana RPC ({type(exc).__name__}). Try again in a minute.")
        return out
    if balance >= FUNDED_LAMPORTS:
        out.append(f"✓ Balance {balance / LAMPORTS_PER_SOL:g} SOL — already funded.")
    else:
        funded, note = request_airdrop(client, keypair.pubkey(), sleep=sleep)
        if funded:
            out.append(f"✓ Received 1 {network} SOL ({note}).")
        else:
            out.append(f"✗ The {network} faucet didn't pay out ({note}). Fund the wallet by hand:")
            out.append(f"  address: {keypair.pubkey()}")
            out.extend(f"  {url}" for url in FAUCET_URLS)

    out.append("Next: `hermes gateway restart` so every Hermes process sees the wallet, then try:")
    out.append("  /sightline grant 0.05 SOL to <address> for 1h max 0.01")
    out.append('  and ask: "send 0.01 SOL to <address>"')
    return out
