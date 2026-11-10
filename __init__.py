"""Sightline: a Solana transaction firewall for Hermes Agent."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

TOOLSET = "sightline"


def _pre_tool_call(tool_name: str = "", **kwargs):
    """Firewall hook. Only sightline_pay is gated; any failure blocks (fail closed)."""
    if tool_name != "sightline_pay":
        return None
    try:
        from .sightline.gate import pre_tool_call
    except Exception as exc:
        logger.exception("sightline: firewall unavailable")
        return {"action": "block", "message": f"Sightline blocked: firewall unavailable ({type(exc).__name__})."}
    return pre_tool_call(tool_name=tool_name, **kwargs)


def register(ctx) -> None:
    from .sightline.tools import TOOLS

    for schema, handler in TOOLS:
        ctx.register_tool(
            name=schema["name"],
            toolset=TOOLSET,
            schema=schema,
            handler=handler,
            description=schema["description"],
        )
    ctx.register_hook("pre_tool_call", _pre_tool_call)

    def _command(raw_args: str = "", **kwargs) -> str:
        """/sightline — typed by the human. The model has no tool that reaches this."""
        try:
            from .sightline.commands import handle
        except Exception as exc:
            return f"Sightline unavailable: {type(exc).__name__}"
        return handle(raw_args, ask=getattr(ctx, "ask_choice", None))

    ctx.register_command(
        "sightline",
        handler=_command,
        description="Sightline wallet firewall: setup, grant, grants, revoke, log, verify",
        args_hint="setup|grant|grants|revoke|log|verify",
    )
