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

    # `hermes sightline …` in a terminal: first-run setup without a model, plus read-only and
    # narrowing commands. Deliberately NO `grant` here — the agent's own terminal tool can run
    # shell commands, so a CLI grant would be a path for a prompt-injected agent to authorise itself.
    register_cli = getattr(ctx, "register_cli_command", None)
    if register_cli is not None:
        def _cli_setup(parser):
            parser.add_argument("subcommand", choices=CLI_SUBCOMMANDS, help="what to do")
            parser.add_argument("rest", nargs="*", help="arguments, e.g. a grant id for revoke")

        def _cli_run(args):
            from .sightline.commands import handle

            print(handle(" ".join([args.subcommand, *args.rest])))

        register_cli("sightline", help="Sightline wallet firewall: setup, grants, revoke, log, verify",
                     setup_fn=_cli_setup, handler_fn=_cli_run,
                     description="Create grants with /sightline grant inside a Hermes chat; the CLI can't.")


CLI_SUBCOMMANDS = ("setup", "grants", "revoke", "log", "verify")
