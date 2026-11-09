"""Sightline backend for the Desktop pane, mounted by Hermes at /api/plugins/sightline/.

    GET  /state            read-only snapshot (network, pubkey, balances, grants, recent audit)
    POST /revoke {"id"}    revoke one grant — narrows permissions only

There is deliberately no route that creates, widens or extends a grant: those stay
behind the human-typed /sightline slash command. Responses never contain the key.

Hermes imports this file on its own (not as part of the plugin package), so the
package is resolved from the already-loaded agent plugin when present, else loaded
from the folder above.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

_PKG_DIR = Path(__file__).resolve().parent.parent / "sightline"
_GRANT_ID = re.compile(r"^g_[0-9a-f]{4,6}$")


def _core():
    """The ``sightline`` package: the agent plugin's copy if loaded, else a private load."""
    for name in ("hermes_plugins.sightline.sightline", "sightline_dashboard_core"):
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "__path__"):
            return name
    name = "sightline_dashboard_core"
    spec = importlib.util.spec_from_file_location(name, _PKG_DIR / "__init__.py",
                                                  submodule_search_locations=[str(_PKG_DIR)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return name


def _state_module():
    return importlib.import_module(f"{_core()}.state")


class RevokeBody(BaseModel):
    id: str


@router.get("/state")
def state(limit: int = 50):
    return _state_module().get_state(limit=max(1, min(limit, 200)))


@router.post("/revoke")
def revoke(body: RevokeBody):
    if not _GRANT_ID.match(body.id or ""):
        raise HTTPException(status_code=400, detail="bad grant id")
    result = _state_module().revoke(body.id)
    if not result["ok"] and result["error"] == "not_found":
        raise HTTPException(status_code=404, detail=result["message"])
    return result
