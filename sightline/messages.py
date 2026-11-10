"""One place for what each failure means and what to do next.

Every error Sightline returns carries ``error`` (a stable code), ``message`` (what
happened) and ``next_step`` (the exact thing to do). Tool results, block messages,
slash commands and the Desktop pane all use these. No tracebacks, no secrets.
"""

from __future__ import annotations

SETUP = "Run `/sightline setup` in Hermes (or `python scripts/setup_devnet.py`), then `hermes gateway restart`."
FAUCET_URLS = ("https://faucet.solana.com", "https://faucet.quicknode.com/solana/devnet")

NEXT_STEP = {
    "missing_secret": "No wallet is configured. " + SETUP,
    "invalid_secret": ("Set SIGHTLINE_SECRET_KEY in ~/.hermes/.env to a base58 secret key or the JSON "
                       "byte array from a Solana CLI keypair file, then `hermes gateway restart`. "
                       "Or remove it and run `/sightline setup` to create a new devnet wallet."),
    "mainnet_refused": ("Sightline runs on devnet by default. To use mainnet with real funds, set "
                        "SIGHTLINE_ALLOW_MAINNET=1 in ~/.hermes/.env and restart Hermes; otherwise unset "
                        "SIGHTLINE_RPC_URL to go back to devnet."),
    "rpc_timeout": "The Solana RPC did not answer in time. Try again in a minute, or set SIGHTLINE_RPC_URL to another RPC.",
    "rpc_error": "The Solana RPC returned an error. Try again, or set SIGHTLINE_RPC_URL to another RPC endpoint.",
    "invalid_address": "Check the recipient: it must be a Solana address (32–44 base58 characters).",
    "unknown_token": "Use SOL, a known symbol (USDC) or the token's mint address.",
    "unknown_mint": "Check the mint address and that it exists on this network.",
    "invalid_amount": "Give a positive amount in whole units, e.g. 0.01 for 0.01 SOL.",
    "empty_wallet": ("The wallet has no SOL to pay fees. Fund it: `/sightline setup` requests devnet SOL, or "
                     "paste the address into https://faucet.solana.com."),
    "insufficient_funds": "Send less, or fund the wallet (devnet: `/sightline setup` or https://faucet.solana.com).",
    "insufficient_token": "The wallet holds less of this token than requested. Check `sightline_balance` and send less.",
    "blockhash_expired": "The network was slow and the transaction expired before landing. Nothing was sent; try again.",
    "unconfirmed": "It was sent but not confirmed in time. Check the explorer link before retrying, to avoid paying twice.",
    "send_failed": "Nothing was sent. Run `sightline_preview` with the same arguments to see why.",
    "simulation_failed": "Nothing was sent. Run `sightline_preview` with the same arguments to see why.",
    "approval_missing": "Ask again so Hermes can show you the approval prompt, or create a grant with /sightline grant.",
    "faucet_rate_limited": "Fund the wallet by hand: paste the address into " + " or ".join(FAUCET_URLS) + ".",
    "missing_dependency": "Run `hermes plugins enable sightline` (it installs solana + solders), then restart Hermes.",
    "internal_error": "Nothing was sent. Run `hermes logs` for details and report it if it repeats.",
}

# Firewall rule → what the user can do about a BLOCK / APPROVE.
RULE_STEP = {
    "no_grant": "Approve this one payment when Hermes asks, or create a grant: /sightline grant <cap> <token> to <address> for 1h",
    "sol_reserve": "Sightline keeps 0.01 SOL for fees. Send less.",
    "token_fraction": "Sightline won't send more than 90% of a token balance at once. Send less, or split it.",
    "mismatch": "The simulated result differs from the request. Do not retry; check the recipient and token.",
    "unknown_program": "The transaction calls a program outside the safe set. Sightline only sends plain transfers.",
    "forbidden_instruction": "The transaction contains an instruction Sightline never signs.",
    "simulation": "Nothing was sent. Run `sightline_preview` with the same arguments to see why.",
    "mainnet": NEXT_STEP["mainnet_refused"],
    "approval_missing": NEXT_STEP["approval_missing"],
}


def next_step(code: str | None) -> str:
    return NEXT_STEP.get(code or "", NEXT_STEP["internal_error"])


def rule_step(rule: str | None) -> str:
    if rule and rule.startswith("grant "):
        return ""
    return RULE_STEP.get(rule or "", "")


def error_dict(code: str, message: str, **extra) -> dict:
    return {"error": code, "message": message, "next_step": next_step(code), **extra}
