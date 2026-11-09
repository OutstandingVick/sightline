import json

import yaml

from conftest import ROOT


def test_register_matches_manifest(plugin, ctx):
    plugin.register(ctx)
    manifest = yaml.safe_load((ROOT / "plugin.yaml").read_text())
    assert sorted(ctx.tools) == sorted(manifest["provides_tools"])
    assert sorted(ctx.hooks) == sorted(manifest["provides_hooks"])


def test_status_never_leaks_secret(plugin, ctx, monkeypatch):
    from solders.keypair import Keypair

    kp = Keypair()
    secret = str(kp)
    monkeypatch.setenv("SIGHTLINE_SECRET_KEY", secret)
    monkeypatch.delenv("SIGHTLINE_RPC_URL", raising=False)
    plugin.register(ctx)
    raw = ctx.tools["sightline_status"]["handler"]({})
    out = json.loads(raw)
    assert out == {"network": "devnet", "rpc_url": "https://api.devnet.solana.com",
                   "public_key": str(kp.pubkey())}
    assert secret not in raw


def test_hook_allows(plugin, ctx):
    plugin.register(ctx)
    assert ctx.hooks["pre_tool_call"][0](tool_name="sightline_status", args={}) is None


def test_every_tool_description_states_devnet_default(plugin, ctx):
    plugin.register(ctx)
    for name, tool in ctx.tools.items():
        assert "devnet by default" in tool["schema"]["description"], name
