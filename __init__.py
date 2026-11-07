"""Sightline: a Solana transaction firewall for Hermes Agent."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

TOOLSET = "sightline"


def _pre_tool_call(tool_name: str = "", **kwargs) -> None:
    """Placeholder firewall hook: log Sightline tool calls, allow everything."""
    if tool_name.startswith("sightline_"):
        logger.info("sightline: pre_tool_call %s", tool_name)
    return None


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
