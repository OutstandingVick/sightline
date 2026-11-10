"""Create (or reuse) a Sightline devnet wallet and fund it from the faucet.

Usage:  python scripts/setup_devnet.py [--no-airdrop]

Same as typing `/sightline setup` in Hermes. Needs `solana` and `solders`
(`pip install "solana>=0.36,<0.37" "solders>=0.26,<0.27"`). Saves the key to
$HERMES_HOME/.env (default ~/.hermes/.env) as SIGHTLINE_SECRET_KEY and never prints it.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

try:
    from sightline import setup
except ModuleNotFoundError as exc:
    sys.exit(f"Missing Python package {exc.name!r}. Run: pip install \"solana>=0.36,<0.37\" \"solders>=0.26,<0.27\"")


def main() -> None:
    for line in setup.run(airdrop="--no-airdrop" not in sys.argv[1:]):
        print(line)


if __name__ == "__main__":
    main()
