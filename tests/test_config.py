import pytest

from sightline.config import MAINNET_GENESIS_HASH, ConfigError, load_settings, network_from_url


@pytest.mark.parametrize("url,net", [
    ("https://api.devnet.solana.com", "devnet"),
    ("https://api.mainnet-beta.solana.com", "mainnet"),
    ("https://api.testnet.solana.com", "testnet"),
    ("http://127.0.0.1:8899", "custom"),
])
def test_network_from_url(url, net):
    assert network_from_url(url) == net


def test_defaults_to_devnet(keypair):
    s = load_settings()
    assert s.network == "devnet" and s.public_key == keypair.pubkey()


def test_mainnet_refused_without_flag(keypair, monkeypatch):
    monkeypatch.setenv("SIGHTLINE_RPC_URL", "https://api.mainnet-beta.solana.com")
    with pytest.raises(ConfigError) as e:
        load_settings()
    assert e.value.code == "mainnet_refused"


def test_mainnet_allowed_with_flag(keypair, monkeypatch):
    monkeypatch.setenv("SIGHTLINE_RPC_URL", "https://api.mainnet-beta.solana.com")
    monkeypatch.setenv("SIGHTLINE_ALLOW_MAINNET", "1")
    assert load_settings().network == "mainnet"


def test_custom_rpc_on_mainnet_genesis_refused(keypair, monkeypatch):
    monkeypatch.setenv("SIGHTLINE_RPC_URL", "https://my-rpc.example.com")
    s = load_settings()
    with pytest.raises(ConfigError):
        s.check_genesis(MAINNET_GENESIS_HASH)


def test_explorer_url(keypair, monkeypatch):
    assert load_settings().explorer_url("SIG").endswith("/tx/SIG?cluster=devnet")
    monkeypatch.setenv("SIGHTLINE_RPC_URL", "https://api.mainnet-beta.solana.com")
    monkeypatch.setenv("SIGHTLINE_ALLOW_MAINNET", "1")
    assert load_settings().explorer_url("SIG") == "https://explorer.solana.com/tx/SIG"


def test_missing_and_invalid_secret(monkeypatch):
    monkeypatch.delenv("SIGHTLINE_SECRET_KEY", raising=False)
    with pytest.raises(ConfigError, match="not set"):
        load_settings()
    monkeypatch.setenv("SIGHTLINE_SECRET_KEY", "garbage")
    with pytest.raises(ConfigError) as e:
        load_settings()
    assert "garbage" not in e.value.message


def test_settings_repr_hides_keypair(keypair):
    assert str(keypair) not in repr(load_settings())
