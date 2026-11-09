import pytest

from sightline import audit, grants
from sightline.commands import UsageError, handle, parse_duration, parse_grant

A = "7xKqGNm1r5h6tqk3Vb3vKXg6wZ8bq4o5bS2mF8yQ9fP2"
B = "535pnQVzoGKSkvTpwEm8WaAHZeRRkUvwi2HCw8M9CyBg"
USDC = "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU"


@pytest.fixture(autouse=True)
def devnet(monkeypatch):
    monkeypatch.delenv("SIGHTLINE_RPC_URL", raising=False)


def test_parse_full_grant():
    p = parse_grant(["5", "usdc", "to", f"{A},{B}", "for", "1h", "max", "2", "note", "coffee run"])
    assert p["token"] == USDC and p["symbol"] == "USDC" and str(p["daily_cap"]) == "5"
    assert str(p["max_per_tx"]) == "2" and p["recipients"] == [A, B] and p["duration_s"] == 3600
    assert p["note"] == "coffee run" and p["network"] == "devnet"


def test_defaults_24h_and_cap_as_max():
    g = grants.get(handle(f"grant 1 SOL to {A}").split()[1].rstrip(":"))
    assert g.max_per_tx == g.daily_cap == "1" and round(g.expires_at - g.created_at) == 86400


def test_recipients_required_and_any_is_explicit():
    with pytest.raises(UsageError, match="to <addr>"):
        parse_grant(["1", "SOL"])
    assert parse_grant(["1", "SOL", "to", "any"])["recipients"] == ["*"]
    assert "ANY recipient" in handle("grant 1 SOL to any")


@pytest.mark.parametrize("bad", ["grant", "grant x SOL to any", "grant 1 DOGE to any",
                                 f"grant 1 SOL to {A} for 0h", f"grant 1 SOL to {A} max 2",
                                 "grant 1 SOL to notanaddress", f"grant 1 SOL to {A} for"])
def test_bad_grants_show_usage(bad):
    out = handle(bad)
    assert "Usage:" in out and not grants.list_grants()


def test_duration():
    assert parse_duration("30m") == 1800 and parse_duration("7d") == 604800
    with pytest.raises(UsageError):
        parse_duration("1w")


def test_grants_revoke_log_verify_flow():
    assert handle("grants").startswith("No grants")
    out = handle(f'grant 5 USDC to {A} for 1h max 2 note "lunch"')
    gid = out.split()[1].rstrip(":")
    assert out.startswith(f"Granted {gid}: the agent may send up to 5 USDC per rolling 24h (max 2 per tx)")
    listing = handle("grants")
    assert gid in listing and "5/5 USDC left today" in listing and '"lunch"' in listing
    assert handle(f"revoke {gid}") == f"Revoked {gid}. It no longer authorises any payment."
    assert "revoked" in handle("grants")
    log = handle("log 5")
    assert "grant_created" not in log and f"grant {gid} created" in log and f"grant {gid} revoked" in log
    assert handle("verify").startswith("✓ 2 entries, chain intact")


def test_revoke_all_and_unknown():
    handle(f"grant 1 SOL to {A}")
    handle(f"grant 1 SOL to {B}")
    assert handle("revoke all").startswith("Revoked 2 grant(s)")
    assert handle("revoke g_none") == "No grant g_none."


def test_revoke_picker_uses_ask_choice():
    gid = handle(f"grant 1 SOL to {A}").split()[1].rstrip(":")
    asked = []

    def ask(question, choices):
        asked.append([c["value"] for c in choices])
        return gid

    assert handle("revoke", ask=ask).startswith(f"Revoked {gid}")
    assert asked == [[gid, "all"]]


def test_help_and_unknown():
    assert handle("").startswith("Usage:") and "Unknown subcommand" in handle("frobnicate")


def test_verify_reports_tampering(db_path):
    import sqlite3

    handle(f"grant 1 SOL to {A}")
    conn = sqlite3.connect(db_path)
    conn.execute("""UPDATE audit SET data = replace(data, '"1"', '"999"')""")
    conn.commit()
    assert handle("verify").startswith("✗ chain broken")
    assert audit.verify()[0] is False
