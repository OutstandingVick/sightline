"""Enforcement: the pre_tool_call hook and the hand-off to the tool handler.

The hook runs for ``sightline_pay`` only. It builds the intent, simulates it, asks the
firewall, and returns Hermes' block / approve directive (or None to allow). The result
is cached for a short time, keyed by (session, exact arguments), so the handler can
reuse the simulation and knows whether a human approved this specific call.

The handler (``execute_intent``) always re-runs the firewall itself. A cached APPROVE
is the only evidence of human approval; it is consumed on first use, expires after
TTL seconds, and is replaced whenever the hook evaluates the same call again. If the
hook never ran, an APPROVE verdict is treated as BLOCK.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass

from . import audit
from .firewall import ALLOW, APPROVE, BLOCK, Decision

logger = logging.getLogger(__name__)

TTL = 30.0
GUARDED_TOOLS = frozenset({"sightline_pay"})

_lock = threading.Lock()
_cache: dict[str, "Evaluation"] = {}


@dataclass
class Evaluation:
    ts: float
    intent: object
    built: object
    preview: object
    decision: Decision


def cache_key(args: dict, session_id: str = "") -> str:
    canon = {"recipient": str(args.get("recipient", "")).strip(), "amount": str(args.get("amount")),
             "token": str(args.get("token") or "SOL").strip().upper(), "link": str(args.get("link") or "").strip()}
    return hashlib.sha256(f"{session_id}|{json.dumps(canon, sort_keys=True)}".encode()).hexdigest()


def remember(key: str, ev: Evaluation) -> None:
    with _lock:
        now = time.time()
        for k in [k for k, v in _cache.items() if now - v.ts > TTL]:
            del _cache[k]
        _cache[key] = ev


def take(key: str) -> Evaluation | None:
    """Pop a fresh evaluation for this exact call (single use)."""
    with _lock:
        ev = _cache.pop(key, None)
    if ev is None or time.time() - ev.ts > TTL:
        return None
    return ev


def log_decision(intent: dict, decision: Decision, explanation: str, source: str, conn=None) -> None:
    try:
        audit.append("decision", {"source": source, **decision.to_dict(), "intent": intent,
                                  "explanation": explanation}, conn=conn)
    except Exception:  # logging must never turn a block into an allow
        logger.exception("sightline: audit write failed")


def pre_tool_call(tool_name: str = "", args: dict | None = None, session_id: str = "", **kwargs):
    if tool_name not in GUARDED_TOOLS:
        return None
    try:
        return _evaluate_hook(args or {}, session_id)
    except Exception as exc:  # anything unexpected: fail closed
        logger.exception("sightline: firewall hook failed")
        return {"action": "block", "message": f"Sightline BLOCK: firewall error ({type(exc).__name__}). Nothing was sent.\n"
                                              "Next: run `hermes logs` for details."}


def _evaluate_hook(args: dict, session_id: str):
    from dataclasses import asdict

    from .config import load_settings
    from .firewall import decide
    from .intents import _preview, pay_intent
    from .wallet import Wallet

    try:
        wallet = Wallet(load_settings())
        intent = pay_intent(wallet, args.get("recipient", ""), args.get("amount"), args.get("token") or "SOL",
                            link=args.get("link"))
        built, preview = _preview(wallet, intent)
    except Exception as exc:
        from .messages import next_step

        message = getattr(exc, "message", None) or type(exc).__name__
        code = getattr(exc, "code", None) or "internal_error"
        return {"action": "block", "message": f"Sightline BLOCK: {message}\nNext: {next_step(code)}"}
    decision = decide(intent, preview.simulation, wallet.settings)
    remember(cache_key(args, session_id), Evaluation(time.time(), intent, built, preview, decision))
    log_decision(asdict(intent), decision, preview.explanation, "hook")
    if decision.verdict == BLOCK:
        from .messages import next_step, rule_step

        sim = preview.simulation
        failed = not sim.ok and decision.rule in ("simulation", "no_grant")
        step = next_step(sim.error_code) if failed else rule_step(decision.rule)
        return {"action": "block",
                "message": f"Sightline BLOCK: {decision.reason}\n{preview.explanation}" + (f"\nNext: {step}" if step else "")}
    if decision.verdict == APPROVE:
        return {
            "action": "approve",
            "message": (f"Sightline APPROVE needed. {preview.explanation}\n"
                        f"No grant covers this: {decision.reason}. Approve this one payment?"),
            # Unique per request: Hermes' "always"/"session" answers must never become a
            # blanket approval for future payments.
            "rule_key": f"sightline:{secrets.token_hex(8)}",
        }
    assert decision.verdict == ALLOW
    return None
