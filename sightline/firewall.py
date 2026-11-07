"""Firewall.

Future role: the policy engine behind the ``pre_tool_call`` hook. Checks the
call against active grants and its simulation, then returns ``None``,
``{"action": "approve", ...}`` or ``{"action": "block", ...}``.
"""
