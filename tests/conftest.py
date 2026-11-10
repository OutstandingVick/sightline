import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # makes the inner `sightline` package importable


class FakeCtx:
    def __init__(self):
        self.tools, self.hooks = {}, {}

    def register_tool(self, name, toolset, schema, handler, **kwargs):
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler}

    def register_hook(self, hook_name, callback, **kwargs):
        self.hooks.setdefault(hook_name, []).append(callback)

    def register_command(self, name, handler, description="", args_hint=""):
        self.commands = getattr(self, "commands", {})
        self.commands[name] = handler


@pytest.fixture(scope="session")
def plugin():
    spec = importlib.util.spec_from_file_location(
        "sightline_plugin", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def ctx():
    return FakeCtx()


@pytest.fixture
def keypair(monkeypatch):
    from solders.keypair import Keypair

    kp = Keypair()
    monkeypatch.setenv("SIGHTLINE_SECRET_KEY", str(kp))
    monkeypatch.delenv("SIGHTLINE_RPC_URL", raising=False)
    monkeypatch.delenv("SIGHTLINE_ALLOW_MAINNET", raising=False)
    return kp


@pytest.fixture(autouse=True)
def cluster(monkeypatch, request):
    """Every test simulates against an in-memory cluster (never the network)."""
    import importlib

    from fakes import FakeCluster

    request.getfixturevalue("plugin")  # make sure the Hermes-style module copy exists too
    fake = FakeCluster()
    for name in ("sightline.simulate", "sightline_plugin.sightline.simulate"):
        try:
            mod = importlib.import_module(name)
        except ImportError:
            continue
        monkeypatch.setattr(mod, "_post", fake)
    return fake


@pytest.fixture(autouse=True)
def db_path(tmp_path, monkeypatch):
    """Each test gets its own grants/audit database."""
    path = tmp_path / "sightline.db"
    monkeypatch.setenv("SIGHTLINE_DB_PATH", str(path))
    return path


@pytest.fixture
def grant_any():
    """A generous SOL grant to any recipient, as if the user had typed /sightline grant."""
    from decimal import Decimal

    from sightline import grants

    return grants.create(network="devnet", token="SOL", symbol="SOL", daily_cap=Decimal(100),
                         max_per_tx=None, recipients=["*"], duration_s=3600)


# Test files whose cases are attacks on the firewall: prompt-injected payments, forged or
# widened permissions, key leakage, log tampering, bypassing the hook. `pytest -m attack`.
ATTACK_FILES = {"test_firewall.py", "test_gate.py", "test_no_secret_leak.py", "test_model_cannot_grant.py",
                "test_audit.py", "test_plugin_api.py"}


def pytest_collection_modifyitems(items):
    for item in items:
        if item.path.name in ATTACK_FILES:
            item.add_marker(pytest.mark.attack)
